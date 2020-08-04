from datetime import datetime
import time

from unittest.mock import patch

from rest_framework.reverse import reverse
from shared.torngit.exceptions import TorngitClientError

from codecov.tests.base_test import InternalAPITest
from codecov_auth.tests.factories import OwnerFactory
from core.tests.factories import RepositoryFactory, CommitFactory, PullFactory, BranchFactory
from core.models import Repository


class RepositoryViewSetTestSuite(InternalAPITest):
    def _list(self, kwargs={}, query_params={}):
        if kwargs == {}:
            kwargs={"service": self.org.service, "owner_username": self.org.username}

        return self.client.get(
            reverse('repos-list', kwargs=kwargs),
            data=query_params
        )

    def _retrieve(self, kwargs={}, data={}):
        if kwargs == {}:
            kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name}
        return self.client.get(reverse('repos-detail', kwargs=kwargs), data=data)

    def _update(self, kwargs={}, data={}):
        if kwargs == {}:
            kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name}
        return self.client.patch(
            reverse('repos-detail', kwargs=kwargs),
            data=data,
            content_type="application/json"
        )

    def _destroy(self, kwargs={}):
        if kwargs == {}:
            kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name}
        return self.client.delete(reverse('repos-detail', kwargs=kwargs))

    def _regenerate_upload_token(self, kwargs={}):
        if kwargs == {}:
            kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name}
        return self.client.patch(reverse('repos-regenerate-upload-token', kwargs=kwargs))

    def _erase(self, kwargs={}):
        if kwargs == {}:
            kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name}
        return self.client.patch(reverse('repos-erase', kwargs=kwargs))

    def _encode(self, kwargs, data):
        return self.client.post(reverse('repos-encode', kwargs=kwargs), data=data)

    def _reset_webhook(self, kwargs={}):
        if kwargs == {}:
            kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name}
        return self.client.put(reverse('repos-reset-webhook', kwargs=kwargs))


class TestRepositoryViewSetList(RepositoryViewSetTestSuite):
    def setUp(self):
        self.org = OwnerFactory(username='codecov', service='github')

        self.repo1 = RepositoryFactory(author=self.org, active=True, private=True, name='A')
        self.repo2 = RepositoryFactory(author=self.org, active=True, private=True, name='B')

        repos_with_permission = [
            self.repo1.repoid,
            self.repo2.repoid,
        ]

        self.user = OwnerFactory(
            username='codecov-user',
            service='github',
            organizations=[self.org.ownerid],
            permission=repos_with_permission
        )

        self.client.force_login(user=self.user)

    def test_order_by_updatestamp(self):
        response = self._list(
            query_params={'ordering': 'updatestamp'}
        )

        assert response.data["results"][0]["repoid"] == self.repo1.repoid
        assert response.data["results"][1]["repoid"] == self.repo2.repoid

        reverse_response = self._list(
            query_params={'ordering': '-updatestamp'}
        )

        assert reverse_response.data["results"][0]["repoid"] == self.repo2.repoid
        assert reverse_response.data["results"][1]["repoid"] == self.repo1.repoid

    def test_order_by_name(self):
        response = self._list(
            query_params={'ordering': 'name'}
        )

        assert response.data["results"][0]["repoid"] == self.repo1.repoid
        assert response.data["results"][1]["repoid"] == self.repo2.repoid

        reverse_response = self._list(
            query_params={'ordering': '-name'}
        )

        assert reverse_response.data["results"][0]["repoid"] == self.repo2.repoid
        assert reverse_response.data["results"][1]["repoid"] == self.repo1.repoid

    def test_order_by_coverage(self):
        default_totals = {
            "f": 1,
            "n": 4,
            "h": 4,
            "m": 0,
            "p": 0,
            "c": 100.0,
            "b": 0,
            "d": 0,
            "s": 1,
            "C": 0.0,
            "N": 0.0,
            "diff": ""
        }

        CommitFactory(repository=self.repo1, totals={**default_totals, "c": 25})
        CommitFactory(repository=self.repo1, totals={**default_totals, "c": 41})
        CommitFactory(repository=self.repo2, totals={**default_totals, "c": 32})

        response = self._list(
            query_params={'ordering': 'coverage'}
        )

        assert response.data["results"][0]["repoid"] == self.repo2.repoid
        assert response.data["results"][1]["repoid"] == self.repo1.repoid

        reverse_response = self._list(
            query_params={'ordering': '-coverage'}
        )

        assert reverse_response.data["results"][0]["repoid"] == self.repo1.repoid
        assert reverse_response.data["results"][1]["repoid"] == self.repo2.repoid

    def test_totals_serializer(self):
        default_totals = {
            "f": 1,
            "n": 4,
            "h": 4,
            "m": 0,
            "p": 0,
            "c": 100.0,
            "b": 0,
            "d": 0,
            "s": 1,
            "C": 0.0,
            "N": 0.0,
            "diff": ""
        }

        CommitFactory(repository=self.repo1, totals=default_totals)
        # Make sure we only get the commit from the default branch
        CommitFactory(repository=self.repo1, totals={**default_totals, 'c': 90.0}, branch='other')

        response = self._list(
            query_params={'names': 'A'}
        )

        assert response.data["results"][0]["totals"]["files"] == default_totals['f']
        assert response.data["results"][0]["totals"]["lines"] == default_totals['n']
        assert response.data["results"][0]["totals"]["hits"] == default_totals['h']
        assert response.data["results"][0]["totals"]["misses"] == default_totals['m']
        assert response.data["results"][0]["totals"]["partials"] == default_totals['p']
        assert response.data["results"][0]["totals"]["coverage"] == default_totals['c']
        assert response.data["results"][0]["totals"]["branches"] == default_totals['b']
        assert response.data["results"][0]["totals"]["methods"] == default_totals['d']
        assert response.data["results"][0]["totals"]["sessions"] == default_totals['s']
        assert response.data["results"][0]["totals"]["complexity"] == default_totals['C']
        assert response.data["results"][0]["totals"]["complexity_total"] == default_totals['N']
        assert response.data["results"][0]["totals"]["complexity_ratio"] == 0

    def test_get_totals_with_timestamp(self):
        default_totals = {
            "f": 1,
            "n": 4,
            "h": 4,
            "m": 0,
            "p": 0,
            "c": 100.0,
            "b": 0,
            "d": 0,
            "s": 1,
            "C": 0.0,
            "N": 0.0,
            "diff": ""
        }
        older_coverage = 90.0

        CommitFactory(repository=self.repo1, totals={**default_totals, "c": older_coverage})
        # We're testing that the lte works as expected, so we're not sending the exact same timestamp
        fetching_time = datetime.now().isoformat()

        time.sleep(1)
        CommitFactory(repository=self.repo1, totals=default_totals)

        response = self._list(
            query_params={'names': 'A', 'timestamp': fetching_time}
        )

        assert response.data["results"][0]["totals"]["coverage"] == older_coverage

    def test_get_repos_with_totals(self):
        default_totals = {
            "f": 1,
            "n": 4,
            "h": 4,
            "m": 0,
            "p": 0,
            "c": 100.0,
            "b": 0,
            "d": 0,
            "s": 1,
            "C": 0.0,
            "N": 0.0,
            "diff": ""
        }

        CommitFactory(repository=self.repo1, totals=default_totals)

        response = self._list(
            query_params={'exclude_uncovered': True}
        )

        assert response.data["count"] == 1

    def test_get_active_repos(self):
        RepositoryFactory(author=self.org, name='C')
        response = self._list(
            query_params={'active': True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.data['results']),
            2,
            "got the wrong number of repos: {}".format(len(response.data['results']))
        )

    def test_get_inactive_repos(self):
        new_repo = RepositoryFactory(author=self.org, name='C', private=False)

        response = self._list(
            query_params={'active': False}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.data['results']),
            1,
            "got the wrong number of repos: {}".format(len(response.data['results']))
        )

    def test_get_all_repos(self):
        new_repo = RepositoryFactory(author=self.org, name='C', private=False)

        response = self._list()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.data['results']),
            3,
            "got the wrong number of repos: {}".format(len(response.data['results']))
        )

    def test_get_all_repos_by_name(self):
        new_repo = RepositoryFactory(author=self.org, name='C', private=False)

        response = self._list(
            query_params={'names': 'A,B'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.data['results']),
            2,
            "got the wrong number of repos: {}".format(len(response.data['results']))
        )

    def test_returns_private_repos_if_user_has_permission(self):
        new_repo = RepositoryFactory(author=self.org, name='C')
        self.user.permission.append(new_repo.repoid)
        self.user.save()

        response = self._list()

        assert response.status_code == 200
        assert len(response.data['results']) == 3

    def test_returns_private_repos_if_user_owns_repo(self):
        new_repo = RepositoryFactory(author=self.user, name='C')

        response = self._list({"service": self.user.service, "owner_username": self.user.username})

        assert response.status_code == 200
        assert new_repo.name in [repo["name"] for repo in response.data['results']]

    def test_returns_public_repos_if_not_owned_by_user_and_not_in_permissions_array(self):
        new_repo = RepositoryFactory(author=self.org, name='C', private=False)

        response = self._list()

        assert response.status_code == 200
        assert new_repo.name in [repo["name"] for repo in response.data['results']]

    def test_doesnt_return_private_repos_if_above_conditions_not_met(self):
        # Private repo, not owned by user, not in users permissions array
        private_repo = RepositoryFactory(author=self.org, name='C', private=True)

        response = self._list()

        assert response.status_code == 200
        assert private_repo.name not in [repo["name"] for repo in response.data['results']]


@patch("internal_api.repo.repository_accessors.RepoAccessors.get_repo_permissions")
class TestRepositoryViewSetDetailActions(RepositoryViewSetTestSuite):
    def setUp(self):
        self.org = OwnerFactory(username='codecov', service='github', service_id="5767537")
        self.repo = RepositoryFactory(author=self.org, active=True, private=True, name='repo1', service_id="201298242")

        self.user = OwnerFactory(
            username='codecov-user',
            service='github',
            organizations=[self.org.ownerid]
        )

        self.client.force_login(user=self.user)

    def test_retrieve_with_view_and_edit_permissions_succeeds(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        response = self._retrieve()
        self.assertEqual(response.status_code, 200)
        assert 'upload_token' in response.data

    def test_retrieve_without_read_permissions_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = False, False
        response = self._retrieve()
        assert response.status_code == 403

    def test_retrieve_for_inactive_user_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        self.org.plan = "users-inappy"
        self.org.save()

        response = self._retrieve()
        assert response.status_code == 403
        assert response.data["detail"] == "User not activated"

    def test_retrieve_without_edit_permissions_returns_detail_view_without_upload_token(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, False
        response = self._retrieve()
        assert response.status_code == 200
        assert "upload_token" not in response.data

    def test_destroy_repo_with_admin_rights_succeeds(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        self.org.admins = [self.user.ownerid]
        self.org.save()
        response = self._destroy()
        assert response.status_code == 204
        assert not Repository.objects.filter(name="repo1").exists()

    def test_destroy_repo_without_admin_rights_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        assert self.user.ownerid not in self.org.admins

        response = self._destroy()
        assert response.status_code == 403
        assert Repository.objects.filter(name="repo1").exists()

    def test_destroy_repo_as_inactive_user_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        self.org.admins = [self.user.ownerid]
        self.org.plan = "users-inappy"
        self.org.save()

        response = self._destroy()
        assert response.status_code == 403
        assert response.data["detail"] == "User not activated"
        assert Repository.objects.filter(name="repo1").exists()

    def test_regenerate_upload_token_with_permissions_succeeds(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        old_upload_token = self.repo.upload_token

        response = self._regenerate_upload_token()

        assert response.status_code == 200
        self.repo.refresh_from_db()
        assert str(self.repo.upload_token) == response.data["upload_token"]
        assert str(self.repo.upload_token) != old_upload_token

    def test_regenerate_upload_token_without_permissions_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = False, False
        response = self._regenerate_upload_token()
        self.assertEqual(response.status_code, 403)

    def test_regenerate_upload_token_as_inactive_user_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        self.org.plan = "users-inappy"
        self.org.save()

        response = self._regenerate_upload_token()

        assert response.status_code == 403
        assert response.data["detail"] == "User not activated"

    def test_update_default_branch_with_permissions_succeeds(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        new_default_branch = "dev"

        response = self._update(
            data={'branch': new_default_branch}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['branch'], 'dev', "got unexpected response: {}".format(response.data['branch']))
        self.repo.refresh_from_db()
        assert self.repo.branch == new_default_branch

    def test_update_default_branch_without_write_permissions_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, False
        new_default_branch = "no_write_permissions"

        response = self._update(
            data={'branch': 'dev'}
        )
        self.assertEqual(response.status_code, 403)

    def test_erase_deletes_related_content_and_clears_cache_and_yaml(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        self.org.admins = [self.user.ownerid]
        self.org.save()

        CommitFactory(
            message='test_commits_base',
            commitid='9193232a8fe3429496956ba82b5fed2583d1b5eb',
            repository=self.repo,
        )

        PullFactory(
            pullid=2,
            repository=self.repo,
            author=self.repo.author,
        )

        BranchFactory(authors=[self.org.ownerid], repository=self.repo)

        self.repo.cache = {"cache": "val"}
        self.repo.yaml = {"yaml": "val"}
        self.repo.save()

        response = self._erase()
        assert response.status_code == 200

        assert not self.repo.commits.exists()
        assert not self.repo.pull_requests.exists()
        assert not self.repo.branches.exists()

        self.repo.refresh_from_db()
        assert self.repo.yaml == None
        assert self.repo.cache == None

    def test_erase_without_admin_rights_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        assert self.user.ownerid not in self.org.admins

        response = self._erase()
        assert response.status_code == 403

    def test_erase_as_inactive_user_returns_403(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        self.org.plan = "users-inappy"
        self.org.admins = [self.user.ownerid]
        self.org.save()

        response = self._erase()

        assert response.status_code == 403
        assert response.data["detail"] == "User not activated"

    def test_retrieve_returns_yaml(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, False

        yaml = {"yaml": "val"}
        self.repo.yaml = yaml
        self.repo.save()

        response = self._retrieve()
        assert response.status_code == 200
        assert response.data["yaml"] == yaml

    def test_activation_checks_if_credits_available_for_legacy_users(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        self.org.plan = 'v4-5m'
        self.org.save()

        for i in range(4): # including the one used by other tests, should be 5 total
            RepositoryFactory(name=str(i) + "random", author=self.org, private=True, active=True)

        inactive_repo = RepositoryFactory(author=self.org, private=True, active=False)

        activation_data = {'active': True}
        response = self._update(
            data=activation_data
        )

        assert response.status_code == 403

    def test_encode_returns_200_on_success(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        to_encode = {'value': "hjrok"}
        response = self._encode(
            kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name},
            data=to_encode
        )

        assert response.status_code == 201

    @patch('internal_api.repo.views.encode_secret_string')
    def test_encode_returns_encoded_string_on_success(self, encoder_mock, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        encrypted_string = "string:encrypted string"
        encoder_mock.return_value = encrypted_string

        to_encode = {'value': "hjrok"}
        response = self._encode(
            kwargs={"service": self.org.service, 'owner_username': self.org.username, 'repo_name': self.repo.name},
            data=to_encode
        )

        assert response.status_code == 201
        assert response.data["value"] == encrypted_string

    def test_encode_secret_string_encodes_with_right_key(self, _):
        from internal_api.repo.utils import encode_secret_string

        string_arg = "hi there"
        to_encode = '/'.join(( # this is the format expected by the key
            self.org.service,
            self.org.service_id,
            self.repo.service_id,
            string_arg
        ))

        from shared.encryption import StandardEncryptor
        check_encryptor = StandardEncryptor()
        check_encryptor.key = b']\xbb\x13\xf9}\xb3\xb7\x03)*0Kv\xb2\xcet'

        encoded = encode_secret_string(to_encode)

        # we slice to take off the word "secret" prepended by the util
        assert check_encryptor.decode(encoded[7:]) == to_encode

    def test_repo_bot_returns_username_if_bot_not_null(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        username = 'huecoTanks'
        self.repo.bot = OwnerFactory(username=username)
        self.repo.save()

        response = self._retrieve()

        assert "bot" in response.data
        assert response.data["bot"] == username

    def test_retrieve_with_no_commits_doesnt_crash(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        self.repo.commits.all().delete()

        response = self._retrieve()
        assert response.status_code == 200

    @patch('internal_api.repo.views.delete_webhook_on_provider')
    @patch('internal_api.repo.views.create_webhook_on_provider')
    def test_reset_webhook_unsets_original_hookid_and_sets_new_if_hookid_exists(
        self,
        create_webhook_mock,
        delete_webhook_mock,
        mocked_get_permissions
    ):
        mocked_get_permissions.return_value = True, True

        old_webhook_id, new_webhook_id = "123", "456"

        self.repo.hookid = old_webhook_id
        self.repo.save()

        create_webhook_mock.return_value = new_webhook_id

        response = self._reset_webhook()

        assert response.status_code == 200

        self.repo.refresh_from_db()

        assert self.repo.hookid == new_webhook_id

    @patch('internal_api.repo.views.delete_webhook_on_provider')
    @patch('internal_api.repo.views.create_webhook_on_provider')
    def test_reset_webhook_doesnt_delete_if_no_hookid(
        self,
        create_webhook_mock,
        delete_webhook_mock,
        mocked_get_permissions
    ):
        mocked_get_permissions.return_value = True, True
        create_webhook_mock.return_value = "irrelevant"

        # Make delete function throw exception, so if it's called this test fails
        delete_webhook_mock.side_effect = Exception("Attempted to delete nonexistent webhook")

        response = self._reset_webhook()

    @patch('internal_api.repo.views.delete_webhook_on_provider')
    @patch('internal_api.repo.views.create_webhook_on_provider')
    def test_reset_webhook_creates_new_webhook_even_if_no_hookid(
        self,
        create_webhook_mock,
        delete_webhook_mock,
        mocked_get_permissions
    ):
        mocked_get_permissions.return_value = True, True
        new_webhook_id = "123"
        create_webhook_mock.return_value = new_webhook_id

        response = self._reset_webhook()

        self.repo.refresh_from_db()
        assert self.repo.hookid == new_webhook_id

    @patch('internal_api.repo.views.delete_webhook_on_provider')
    @patch('internal_api.repo.views.create_webhook_on_provider')
    def test_reset_webhook_returns_correct_code_and_response_if_TorgitClientError_raised(
        self,
        create_webhook_mock,
        delete_webhook_mock,
        mocked_get_permissions
    ):
        code = 403
        message = "No can do, buddy"
        mocked_get_permissions.return_value = True, True
        create_webhook_mock.side_effect = TorngitClientError(code=code, response=None, message=message)

        response = self._reset_webhook()

        assert response.status_code == code
        assert response.data == {"detail": message}

    @patch('services.archive.ArchiveService.create_root_storage', lambda _: None)
    @patch('services.archive.ArchiveService.read_chunks', lambda obj, _: '' )
    def test_retrieve_returns_latest_commit_data(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        commit = CommitFactory(repository=self.repo)

        from internal_api.commit.serializers import CommitWithReportSerializer
        expected_commit_payload = CommitWithReportSerializer(commit).data

        response = self._retrieve()
        assert response.status_code == 200
        assert response.data["latest_commit"]["report"]["totals"] == expected_commit_payload["report"]["totals"]

    @patch('services.archive.ArchiveService.create_root_storage', lambda _: None)
    @patch('services.archive.ArchiveService.read_chunks', lambda obj, _: '' )
    def test_retrieve_returns_latest_commit_of_default_branch_if_branch_not_specified(
        self,
        mocked_get_permissions
    ):
        mocked_get_permissions.return_value = True, True

        commit = CommitFactory(repository=self.repo)
        more_recent_commit = CommitFactory(repository=self.repo, branch="other-branch")

        response = self._retrieve()

        assert response.data['latest_commit']['commitid'] == commit.commitid
        assert response.data['latest_commit']['commitid'] != more_recent_commit.commitid

    @patch('services.archive.ArchiveService.create_root_storage', lambda _: None)
    @patch('services.archive.ArchiveService.read_chunks', lambda obj, _: '' )
    def test_retrieve_accepts_branch_query_param_to_specify_latest_commit(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        commit = CommitFactory(repository=self.repo, branch="other-branch")
        more_recent_commit = CommitFactory(repository=self.repo)

        response = self._retrieve(
            data={"branch": "other-branch"}
        )

        assert response.data['latest_commit']['commitid'] == commit.commitid
        assert response.data['latest_commit']['commitid'] != more_recent_commit.commitid

    @patch('services.archive.ArchiveService.create_root_storage', lambda _: None)
    @patch('services.archive.ArchiveService.read_chunks', lambda obj, _: '' )
    def test_latest_commit_is_none_if_dne(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        response = self._retrieve()

        assert response.data['latest_commit'] == None

    def test_can_retrieve_repo_name_containing_dot(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True

        self.repo.name = 'codecov.io'
        self.repo.save()

        response = self._retrieve()
        self.assertEqual(response.status_code, 200)

    # Note (Matt): the only special char that github isn't
    # filtering is .
    def test_can_retrieve_repo_name_containing_special_char(self, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        self.repo.name = "codec@v.i"
        self.repo.save()

        response = self._retrieve()
        self.assertEqual(response.status_code, 200)

    def test_permissions_check_handles_torngit_error(self, mocked_get_permissions):
        err_code, err_message = 403, "yo, no."
        mocked_get_permissions.side_effect = TorngitClientError(
            code=err_code,
            message=err_message,
            response=None
        )
        response = self._retrieve()
        assert response.status_code == err_code
        assert response.data == {"detail": err_message}

    @patch('internal_api.repo.repository_accessors.RepoAccessors.get_repo_details')
    def test_get_object_handles_torngit_error(self, mocked_get_details, mocked_get_perms):
        mocked_get_perms.return_value = True, True
        err_code, err_message = 403, "yo, no."
        mocked_get_details.side_effect = TorngitClientError(
            code=err_code,
            message=err_message,
            response=None
        )
        response = self._retrieve()
        assert response.status_code == err_code
        assert response.data == {"detail": err_message}

    @patch("internal_api.repo.repository_accessors.RepoAccessors.get_repo_details")
    @patch("internal_api.repo.repository_accessors.RepoAccessors.fetch_from_git_and_create_repo")
    def test_create_repo_on_fetch_if_dne(self, mocked_fetch_and_create, mocked_get_repo_details, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        mocked_get_repo_details.return_value = None
        mocked_fetch_and_create.return_value = self.repo

        response = self._retrieve(kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": self.repo.name})
        mocked_fetch_and_create.assert_called()
        mocked_fetch_and_create.assert_called()
        self.assertEqual(response.status_code, 200)

    @patch("internal_api.repo.repository_accessors.RepoAccessors.get_repo_details")
    @patch("internal_api.repo.repository_accessors.RepoAccessors.fetch_from_git_and_create_repo")
    def test_unable_to_fetch_git_repo(self, mocked_fetch_and_create, mocked_get_repo_details, mocked_get_permissions):
        mocked_get_permissions.return_value = True, True
        mocked_get_repo_details.return_value = None
        mocked_fetch_and_create.side_effect = TorngitClientError(code=403, response=None, message="Forbidden")

        response = self._retrieve(kwargs={"service": self.org.service, "owner_username": self.org.username, "repo_name": "new-repo"})
        mocked_fetch_and_create.assert_called()
        mocked_fetch_and_create.assert_called()
        self.assertEqual(response.status_code, 403)