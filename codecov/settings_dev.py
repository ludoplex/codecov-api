from .settings_base import *
import logging


DEBUG = True
ALLOWED_HOSTS = ['localhost']


WEBHOOK_URL = '' # NGROK TUNNEL HERE


STRIPE_API_KEY = 'sk_test_testsn3sc2tirvdea6mqp31t'
STRIPE_ENDPOINT_SECRET = "whsec_testzrff0orrbsv3bdekbbz8cz964dan"
STRIPE_PLAN_IDS = {
    "users-inappm": "plan_F50djuy2tOqnhp",
    "users-inappy": "plan_F50lRPhqk4zZFL"
}


# TODO: dev urls not defined yet -- but defining as such to make tests pass
CLIENT_PLAN_CHANGE_SUCCESS_URL = 'http://localhost:9000'
CLIENT_PLAN_CHANGE_CANCEL_URL = 'http://localhost:9000'


CORS_ORIGIN_WHITELIST = ['localhost:9000', 'localhost']
CORS_ALLOW_CREDENTIALS = True
CODECOV_URL = 'localhost'


GITHUB_CLIENT_ID = "3d44be0e772666136a13"
GITHUB_CLIENT_SECRET = "testrjumu7w1dfvxbr23q9sx3c7u3hgftcf1uho8"
BITBUCKET_CLIENT_ID = "testqmo19ebdkseoby"
BITBUCKET_CLIENT_SECRET = "testfi8hzehvz453qj8mhv21ca4rf83f"
GITLAB_CLIENT_ID = "testq117krewaffvh4y2ktl1cpof8ufldd397vygenzuy24wb220rqg83cdaps4w"
GITLAB_CLIENT_SECRET = "testq19ki95gaa4faunz92a97otmekrwczg60s8wdy3vx1ddfch2rff2oagsozsr"