import asyncio
import hashlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, PropertyMock, patch

import yaml
from django.test import TransactionTestCase
from shared.reports.types import LineSession

import services.comparison as comparison
from codecov_auth.tests.factories import OwnerFactory
from compare.models import CommitComparison
from compare.tests.factories import CommitComparisonFactory
from core.tests.factories import CommitErrorFactory, CommitFactory, RepositoryFactory
from graphql_api.types.enums import UploadErrorEnum, UploadState
from graphql_api.types.enums.enums import UploadType
from reports.tests.factories import (
    CommitReportFactory,
    ReportLevelTotalsFactory,
    RepositoryFlagFactory,
    UploadErrorFactory,
    UploadFactory,
    UploadFlagMembershipFactory,
)
from services.comparison import MissingComparisonReport
from services.profiling import CriticalFile

from .helper import GraphQLTestHelper, paginate_connection

query_commit = """
query FetchCommit($org: String!, $repo: String!, $commit: String!) {
    owner(username: $org) {
        repository(name: $repo) {
            ... on Repository {
                commit(id: $commit) {
                    %s
                }
            }
        }
    }
}
"""

query_commits = """
query FetchCommits($org: String!, $repo: String!) {
    owner(username: $org) {
        repository(name: $repo) {
            ... on Repository {
                commits {
                    edges {
                        node {
                            %s
                        }
                    }
                }
            }
        }
    }
}
"""


class MockCoverage(object):
    def __init__(self, cov):
        self.coverage = cov
        self.sessions = [
            LineSession(0, None),
            LineSession(1, None),
            LineSession(2, None),
        ]


class MockLines(object):
    def __init__(self):
        self.lines = [
            [0, MockCoverage("1/2")],
            [1, MockCoverage(1)],
            [2, MockCoverage(0)],
        ]
        self.totals = MockCoverage(83)


class MockReport(object):
    def get(self, file):
        lines = MockLines()
        return MockLines()

    def filter(self, **kwargs):
        return self

    @property
    def flags(self):
        return {"flag_a": True, "flag_b": True}


class EmptyReport(MockReport):
    def get(self, file):
        return None


class TestCommit(GraphQLTestHelper, TransactionTestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.org = OwnerFactory(username="codecov")
        self.repo = RepositoryFactory(author=self.org, name="gazebo", private=False)
        self.author = OwnerFactory()
        self.parent_commit = CommitFactory(repository=self.repo)
        self.commit = CommitFactory(
            repository=self.repo,
            totals={"c": "12", "diff": [0, 0, 0, 0, 0, "14"]},
            parent_commit_id=self.parent_commit.commitid,
        )
        self.report = CommitReportFactory(commit=self.commit)

        # mock reports for all tests in this class
        self.head_report_patcher = patch(
            "services.comparison.Comparison.head_report", new_callable=PropertyMock
        )
        self.head_report = self.head_report_patcher.start()
        self.head_report.return_value = None
        self.addCleanup(self.head_report_patcher.stop)
        self.base_report_patcher = patch(
            "services.comparison.Comparison.base_report", new_callable=PropertyMock
        )
        self.base_report = self.base_report_patcher.start()
        self.base_report.return_value = None
        self.addCleanup(self.base_report_patcher.stop)

    def test_fetch_commit(self):
        query = (
            query_commit
            % """
            message,
            createdAt,
            commitid,
            state,
            author { username }
        """
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["commitid"] == self.commit.commitid
        assert commit["message"] == self.commit.message
        assert commit["author"]["username"] == self.commit.author.username
        assert commit["state"] == self.commit.state

    def test_fetch_commits(self):
        query = query_commits % "message,commitid,ciPassed"
        self.repo_2 = RepositoryFactory(
            author=self.org, name="test-repo", private=False
        )
        commits_in_db = [
            CommitFactory(
                repository=self.repo_2,
                commitid=123,
                timestamp=datetime.now() - timedelta(days=3),
            ),
            CommitFactory(
                repository=self.repo_2,
                commitid=456,
                timestamp=datetime.now() - timedelta(days=1),
            ),
            CommitFactory(
                repository=self.repo_2,
                commitid=789,
                timestamp=datetime.now() - timedelta(days=2),
            ),
        ]

        variables = {"org": self.org.username, "repo": self.repo_2.name}
        data = self.gql_request(query, variables=variables)
        commits = paginate_connection(data["owner"]["repository"]["commits"])
        commits_commitids = [commit["commitid"] for commit in commits]
        assert commits_commitids == ["456", "789", "123"]

    def test_fetch_parent_commit(self):
        query = query_commit % "parent { commitid } "
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["parent"]["commitid"] == self.parent_commit.commitid

    def test_resolve_commit_without_parent(self):
        self.commit_without_parent = CommitFactory(
            repository=self.repo, parent_commit_id=None
        )
        query = query_commit % "parent { commitid } "
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit_without_parent.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["parent"] is None

    def test_fetch_commit_coverage(self):
        ReportLevelTotalsFactory(report=self.report, coverage=12)
        query = query_commit % "totals { coverage } "
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["totals"]["coverage"] == 12

    def test_fetch_commit_build(self):
        session_one = UploadFactory(report=self.report, provider="circleci")
        session_two = UploadFactory(report=self.report, provider="travisci")
        query = query_commit % "uploads { edges { node { provider } } }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        builds = paginate_connection(commit["uploads"])
        assert builds == [
            {"provider": session_one.provider},
            {"provider": session_two.provider},
        ]

    def test_fetch_commit_uploads_state(self):
        session_one = UploadFactory(
            report=self.report, provider="circleci", state=UploadState.PROCESSED.value
        )
        session_two = UploadFactory(
            report=self.report, provider="travisci", state=UploadState.ERROR.value
        )
        session_three = UploadFactory(
            report=self.report, provider="travisci", state=UploadState.COMPLETE.value
        )
        session_four = UploadFactory(
            report=self.report, provider="travisci", state=UploadState.UPLOADED.value
        )
        query = (
            query_commit
            % """
            uploads {
                edges {
                    node {
                        state
                    }
                }
            }
        """
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        uploads = paginate_connection(commit["uploads"])

        assert uploads == [
            {"state": UploadState.PROCESSED.name},
            {"state": UploadState.ERROR.name},
            {"state": UploadState.COMPLETE.name},
            {"state": UploadState.UPLOADED.name},
        ]

    def test_fetch_commit_uploads(self):
        flag_a = RepositoryFlagFactory(flag_name="flag_a")
        flag_b = RepositoryFlagFactory(flag_name="flag_b")
        flag_c = RepositoryFlagFactory(flag_name="flag_c")
        flag_d = RepositoryFlagFactory(flag_name="flag_d")

        session_a = UploadFactory(
            report=self.report,
            upload_type=UploadType.UPLOADED.value,
            order_number=0,
        )
        UploadFlagMembershipFactory(report_session=session_a, flag=flag_a)
        UploadFlagMembershipFactory(report_session=session_a, flag=flag_b)
        UploadFlagMembershipFactory(report_session=session_a, flag=flag_c)
        session_b = UploadFactory(
            report=self.report,
            upload_type=UploadType.CARRIEDFORWARD.value,
            order_number=1,
        )
        UploadFlagMembershipFactory(report_session=session_b, flag=flag_a)

        session_c = UploadFactory(
            report=self.report,
            upload_type=UploadType.CARRIEDFORWARD.value,
            order_number=2,
        )
        UploadFlagMembershipFactory(report_session=session_c, flag=flag_b)
        session_d = UploadFactory(
            report=self.report,
            upload_type=UploadType.UPLOADED.value,
            order_number=3,
        )
        UploadFlagMembershipFactory(report_session=session_d, flag=flag_b)

        session_e = UploadFactory(
            report=self.report,
            upload_type=UploadType.CARRIEDFORWARD.value,
            order_number=4,
        )
        UploadFlagMembershipFactory(report_session=session_e, flag=flag_d)
        session_f = UploadFactory(
            report=self.report,
            upload_type=UploadType.UPLOADED.value,
            order_number=5,
        )

        query = (
            query_commit
            % """
            uploads {
                edges {
                    node {
                        id
                        uploadType
                        flags
                    }
                }
            }
        """
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        uploads = paginate_connection(commit["uploads"])

        # ordered by upload id, omits uploads with carriedforward flag if another
        # upload exists with the same flag name is is not carriedforward

        assert uploads == [
            {
                "id": 0,
                "uploadType": "UPLOADED",
                "flags": ["flag_a", "flag_b", "flag_c"],
            },
            # TEMP: we're returning ALL uploads for now while we figure out a more
            # performant way to make this query
            {"id": 1, "uploadType": "CARRIEDFORWARD", "flags": ["flag_a"]},
            {"id": 2, "uploadType": "CARRIEDFORWARD", "flags": ["flag_b"]},
            {"id": 3, "uploadType": "UPLOADED", "flags": ["flag_b"]},
            {"id": 4, "uploadType": "CARRIEDFORWARD", "flags": ["flag_d"]},
            {"id": 5, "uploadType": "UPLOADED", "flags": []},
        ]

    def test_fetch_commit_uploads_no_report(self):
        commit = CommitFactory(
            repository=self.repo,
            parent_commit_id=self.commit.commitid,
        )
        query = (
            query_commit
            % """
            uploads {
                edges {
                    node {
                        uploadType
                        flags
                        provider
                    }
                }
            }
        """
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        uploads = paginate_connection(commit["uploads"])
        assert uploads == []

    def test_fetch_commit_uploads_errors(self):
        session = UploadFactory(
            report=self.report, provider="circleci", state=UploadState.ERROR.value
        )
        error_one = UploadErrorFactory(
            report_session=session, error_code=UploadErrorEnum.REPORT_EXPIRED.value
        )
        error_two = UploadErrorFactory(
            report_session=session, error_code=UploadErrorEnum.FILE_NOT_IN_STORAGE.value
        )

        query = (
            query_commit
            % """
            uploads {
                edges {
                    node {
                        errors {
                            edges {
                                node {
                                    errorCode
                                }
                            }
                        }
                    }
                }
            }
        """
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        [upload] = paginate_connection(commit["uploads"])
        errors = paginate_connection(upload["errors"])

        assert errors == [
            {"errorCode": UploadErrorEnum.REPORT_EXPIRED.name},
            {"errorCode": UploadErrorEnum.FILE_NOT_IN_STORAGE.name},
        ]

    def test_yaml_return_default_state_if_default(self):
        org = OwnerFactory(username="default_yaml_owner")
        repo = RepositoryFactory(author=org, private=False)
        commit = CommitFactory(repository=repo)
        query = (
            query_commit
            % """
            yamlState
        """
        )
        variables = {
            "org": org.username,
            "repo": repo.name,
            "commit": commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        assert data["owner"]["repository"]["commit"]["yamlState"] == "DEFAULT"

    def test_fetch_commit_ci(self):
        session_one = UploadFactory(
            report=self.report,
            provider="circleci",
            job_code=123,
            build_code=456,
        )
        query = query_commit % "uploads { edges { node { ciUrl } } }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        uploads = paginate_connection(commit["uploads"])
        assert uploads == [
            {
                "ciUrl": "https://circleci.com/gh/codecov/gazebo/456#tests/containers/123",
            }
        ]

    def test_fetch_download_url(self):
        upload = UploadFactory(
            report=self.report,
            storage_path="v4/raw/2022-06-23/942173DE95CBF167C5683F40B7DB34C0/ee3ecad424e67419d6c4531540f1ef5df045ff12/919ccc6d-7972-4895-b289-f2d569683a17.txt",
        )
        query = query_commit % "uploads { edges { node { downloadUrl } } }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        uploads = paginate_connection(commit["uploads"])
        assert uploads == [
            {
                "downloadUrl": f"http://testserver/upload/gh/{self.org.username}/{self.repo.name}/download?path={upload.storage_path}",
            }
        ]

    @patch(
        "core.commands.commit.commit.CommitCommands.get_final_yaml",
        new_callable=AsyncMock,
    )
    def test_fetch_commit_yaml_call_the_command(self, command_mock):
        query = query_commit % "yaml"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        fake_config = {"codecov": "yes"}
        command_mock.return_value = fake_config
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["yaml"] == yaml.dump(fake_config)

    @patch(
        "services.profiling.ProfilingSummary.critical_files", new_callable=PropertyMock
    )
    @patch("core.commands.commit.commit.CommitCommands.get_file_content")
    @patch("services.report.build_report_from_commit")
    def test_fetch_commit_coverage_file_call_the_command(
        self, report_mock, content_mock, critical_files
    ):
        query = (
            query_commit
            % 'coverageFile(path: "path") { hashedPath, content, isCriticalFile, coverage { line,coverage }, totals {coverage} }'
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
            "path": "path",
        }
        fake_coverage = {
            "content": "file content",
            "coverage": [
                {"line": 0, "coverage": "P"},
                {"line": 1, "coverage": "H"},
                {"line": 2, "coverage": "M"},
            ],
            "totals": {"coverage": 83.0},
        }
        content_mock.return_value = "file content"
        critical_files.return_value = [CriticalFile("path")]

        report_mock.return_value = MockReport()
        data = self.gql_request(query, variables=variables)
        coverageFile = data["owner"]["repository"]["commit"]["coverageFile"]
        assert coverageFile["content"] == fake_coverage["content"]
        assert coverageFile["coverage"] == fake_coverage["coverage"]
        assert coverageFile["totals"] == fake_coverage["totals"]
        assert coverageFile["isCriticalFile"] == True
        assert coverageFile["hashedPath"] == hashlib.md5("path".encode()).hexdigest()

    @patch(
        "services.profiling.ProfilingSummary.critical_files", new_callable=PropertyMock
    )
    @patch("core.commands.commit.commit.CommitCommands.get_file_content")
    @patch("services.report.build_report_from_commit")
    def test_fetch_commit_with_no_coverage_data(
        self, report_mock, content_mock, critical_files
    ):
        query = (
            query_commit
            % 'coverageFile(path: "path") { content, isCriticalFile, coverage { line,coverage }, totals {coverage} }'
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
            "path": "path",
        }
        fake_coverage = {"content": "file content", "coverage": [], "totals": None}
        content_mock.return_value = "file content"
        critical_files.return_value = []

        report_mock.return_value = EmptyReport()
        data = self.gql_request(query, variables=variables)
        coverageFile = data["owner"]["repository"]["commit"]["coverageFile"]
        assert coverageFile["content"] == fake_coverage["content"]
        assert coverageFile["coverage"] == fake_coverage["coverage"]
        assert coverageFile["totals"] == fake_coverage["totals"]
        assert coverageFile["isCriticalFile"] == False

    @patch("services.report.build_report_from_commit")
    def test_flag_names(self, report_mock):
        query = query_commit % "flagNames"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
            "path": "path",
        }
        report_mock.return_value = MockReport()
        data = self.gql_request(query, variables=variables)
        flags = data["owner"]["repository"]["commit"]["flagNames"]
        assert flags == ["flag_a", "flag_b"]

    def test_fetch_commit_compare_call_the_command(self):
        CommitComparisonFactory(
            base_commit=self.parent_commit,
            compare_commit=self.commit,
        )
        query = query_commit % "compareWithParent { ... on Comparison { state } }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["compareWithParent"] == {"state": "pending"}

    def test_fetch_commit_compare_no_parent(self):
        self.commit.parent_commit_id = None
        self.commit.save()

        query = (
            query_commit
            % "compareWithParent { __typename ... on Comparison { state } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["compareWithParent"]["__typename"] == "MissingBaseCommit"

    def test_compare_with_parent_comparison_missing_when_commit_comparison_state_is_errored(
        self,
    ):
        CommitComparisonFactory(
            base_commit=self.parent_commit,
            compare_commit=self.commit,
            state=CommitComparison.CommitComparisonStates.ERROR,
        )
        query = (
            query_commit
            % "compareWithParent { __typename ... on Comparison { state } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["compareWithParent"]["__typename"] == "MissingComparison"

    def test_fetch_commit_compare_no_parent(self):
        self.commit.parent_commit_id = None
        self.commit.save()

        query = (
            query_commit
            % "compareWithParent { __typename ... on Comparison { state } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["compareWithParent"]["__typename"] == "MissingBaseCommit"

    def test_compare_with_parent_change_coverage(self):
        CommitComparisonFactory(
            base_commit=self.parent_commit,
            compare_commit=self.commit,
            state=CommitComparison.CommitComparisonStates.PROCESSED,
        )
        ReportLevelTotalsFactory(
            report=CommitReportFactory(commit=self.parent_commit),
            coverage=75.0,
            files=0,
            lines=0,
            hits=0,
            misses=0,
            partials=0,
            branches=0,
            methods=0,
        )
        ReportLevelTotalsFactory(
            report=self.report,
            coverage=80.0,
            files=0,
            lines=0,
            hits=0,
            misses=0,
            partials=0,
            branches=0,
            methods=0,
        )

        query = (
            query_commit % "compareWithParent { ... on Comparison { changeCoverage } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["compareWithParent"]["changeCoverage"] == 5.0

    def test_compare_with_parent_missing_change_coverage(self):
        CommitComparisonFactory(
            base_commit=self.parent_commit,
            compare_commit=self.commit,
            state=CommitComparison.CommitComparisonStates.PROCESSED,
        )
        ReportLevelTotalsFactory(
            report=CommitReportFactory(commit=self.parent_commit),
            coverage=75.0,
            files=0,
            lines=0,
            hits=0,
            misses=0,
            partials=0,
            branches=0,
            methods=0,
        )

        query = (
            query_commit % "compareWithParent { ... on Comparison { changeCoverage } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["compareWithParent"]["changeCoverage"] is None

    @patch(
        "services.profiling.ProfilingSummary.critical_files", new_callable=PropertyMock
    )
    def test_commit_critical_files(self, critical_files):
        critical_files.return_value = [
            CriticalFile("one"),
            CriticalFile("two"),
            CriticalFile("three"),
        ]

        query = query_commit % "criticalFiles { name }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        assert commit["criticalFiles"] == [
            {"name": "one"},
            {"name": "two"},
            {"name": "three"},
        ]

    def test_commit_yaml_errors(self):
        CommitErrorFactory(commit=self.commit, error_code="invalid_yaml")
        CommitErrorFactory(commit=self.commit, error_code="yaml_client_error")
        query = (
            query_commit
            % "errors(errorType: YAML_ERROR) { edges { node { errorCode } } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        errors = paginate_connection(commit["errors"])
        assert errors == [
            {"errorCode": "invalid_yaml"},
            {"errorCode": "yaml_client_error"},
        ]

    def test_commit_bot_errors(self):
        CommitErrorFactory(commit=self.commit, error_code="repo_bot_invalid")
        CommitErrorFactory(commit=self.commit, error_code="repo_bot_invalid")
        query = (
            query_commit
            % "errors(errorType: BOT_ERROR) { edges { node { errorCode } } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        errors = paginate_connection(commit["errors"])
        assert errors == [
            {"errorCode": "repo_bot_invalid"},
            {"errorCode": "repo_bot_invalid"},
        ]

    def test_fetch_upload_name(self):
        UploadFactory(
            name="First Upload",
            report=self.report,
            job_code=123,
            build_code=456,
        )
        query = query_commit % "uploads { edges { node { name } } }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        uploads = paginate_connection(commit["uploads"])
        assert uploads == [
            {
                "name": "First Upload",
            }
        ]

    @patch("services.comparison.Comparison.validate")
    def test_has_different_number_of_head_and_base_reports_with_invalid_comparison(
        self, mock_compare_validate
    ):
        CommitComparisonFactory(
            base_commit=self.parent_commit,
            compare_commit=self.commit,
            state=CommitComparison.CommitComparisonStates.PROCESSED,
        )
        mock_compare_validate.side_effect = MissingComparisonReport()
        query = (
            query_commit
            % "compareWithParent { ... on Comparison { hasDifferentNumberOfHeadAndBaseReports } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        assert data == {
            "owner": {
                "repository": {
                    "commit": {
                        "compareWithParent": {
                            "hasDifferentNumberOfHeadAndBaseReports": False
                        }
                    }
                }
            }
        }

    def test_fetch_upload_name_is_none(self):
        UploadFactory(
            report=self.report,
            job_code=123,
            build_code=456,
        )
        query = query_commit % "uploads { edges { node { name } } }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        commit = data["owner"]["repository"]["commit"]
        uploads = paginate_connection(commit["uploads"])
        assert uploads == [
            {
                "name": None,
            }
        ]

    def test_fetch_uploads_number(self):
        for _ in range(25):
            UploadFactory(
                report=self.report,
                job_code=123,
                build_code=456,
            )
        query = query_commit % "totalUploads"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        assert data["owner"]["repository"]["commit"]["totalUploads"] == 25

    def test_fetch_all_uploads_is_the_default(self):
        for _ in range(100):
            UploadFactory(
                report=self.report,
                job_code=123,
                build_code=456,
            )
        query = query_commit % "uploads { edges { node { state } } }"
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        assert len(data["owner"]["repository"]["commit"]["uploads"]["edges"]) == 100

    def test_fetch_paginated_uploads(self):
        for _ in range(99):
            UploadFactory(
                report=self.report,
                job_code=123,
                build_code=456,
            )
        query = (
            query_commit
            % "totalUploads, uploads(first: 25) { edges { node { state } } }"
        )
        variables = {
            "org": self.org.username,
            "repo": self.repo.name,
            "commit": self.commit.commitid,
        }
        data = self.gql_request(query, variables=variables)
        assert (data["owner"]["repository"]["commit"]["totalUploads"]) == 99
        assert len(data["owner"]["repository"]["commit"]["uploads"]["edges"]) == 25
