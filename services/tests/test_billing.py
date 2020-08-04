from django.test import TestCase
from django.conf import settings

from unittest.mock import patch
from stripe.error import StripeError

from services.billing import BillingService, StripeService, AbstractPaymentService
from codecov_auth.tests.factories import OwnerFactory


class StripeServiceTests(TestCase):
    def setUp(self):
        self.user = OwnerFactory()
        self.stripe = StripeService(requesting_user=self.user)

    def test_stripe_service_requires_requesting_user_to_be_owner_instance(self):
        with self.assertRaises(Exception):
            StripeService(None)

    @patch('services.billing.stripe.Invoice.list')
    def test_list_invoices_calls_stripe_invoice_list_with_customer_stripe_id(self, invoice_list_mock):
        owner = OwnerFactory(stripe_customer_id=-1)
        self.stripe.list_invoices(owner)
        invoice_list_mock.assert_called_once_with(customer=owner.stripe_customer_id, limit=10)

    @patch('stripe.Invoice.list')
    def test_list_invoices_returns_emptylist_if_stripe_customer_id_is_None(self, invoice_list_mock):
        owner = OwnerFactory()
        invoices = self.stripe.list_invoices(owner)

        invoice_list_mock.assert_not_called()
        assert invoices == []

    @patch('codecov_auth.models.Owner.set_free_plan')
    @patch('services.billing.stripe.Subscription.delete')
    @patch('services.billing.stripe.Subscription.modify')
    def test_delete_subscription_deletes_and_prorates_if_owner_not_on_user_plan(
        self,
        modify_mock,
        delete_mock,
        set_free_plan_mock
    ):
        owner = OwnerFactory(stripe_subscription_id="fowdldjfjwe", plan="v4-50m")
        self.stripe.delete_subscription(owner)
        delete_mock.assert_called_once_with(owner.stripe_subscription_id, prorate=True)
        set_free_plan_mock.assert_called_once()

    @patch('codecov_auth.models.Owner.set_free_plan')
    @patch('services.billing.stripe.Subscription.delete')
    @patch('services.billing.stripe.Subscription.modify')
    def test_delete_subscription_modifies_subscription_to_delete_at_end_of_billing_cycle_if_user_plan(
        self,
        modify_mock,
        delete_mock,
        set_free_plan_mock
    ):
        owner = OwnerFactory(stripe_subscription_id="fowdldjfjwe", plan="users-inappy")
        self.stripe.delete_subscription(owner)
        delete_mock.assert_not_called()
        set_free_plan_mock.assert_not_called()
        modify_mock.assert_called_once_with(owner.stripe_subscription_id, cancel_at_period_end=True)

    @patch('services.billing.stripe.Subscription.modify')
    @patch('services.billing.stripe.Subscription.retrieve')
    def test_modify_subscription_retrieves_subscription_and_modifies_first_item(
        self,
        retrieve_mock,
        modify_mock
    ):
        owner = OwnerFactory(stripe_subscription_id="33043sdf")
        desired_plan_name = "users-inappy"
        desired_user_count = 20
        desired_plan = {
            "value": desired_plan_name,
            "quantity": desired_user_count
        }

        # only including fields relevant to implementation
        subscription_item = {"id": 100}
        retrieve_mock.return_value = {
            "items": {
                "data": [subscription_item]
            }
        }

        self.stripe.modify_subscription(owner, desired_plan)

        modify_mock.assert_called_once_with(
            owner.stripe_subscription_id,
            cancel_at_period_end=False,
            items=[
                {
                    "id": subscription_item["id"],
                    "plan": settings.STRIPE_PLAN_IDS[desired_plan["value"]],
                    "quantity": desired_plan["quantity"]
                }
            ],
            metadata={
                "service": owner.service,
                "obo_organization": owner.ownerid,
                "username": owner.username,
                "obo_name": self.user.name,
                "obo_email": self.user.email,
                "obo": self.user.ownerid
            }
        )

        owner.refresh_from_db()
        assert owner.plan == desired_plan_name
        assert owner.plan_user_count == desired_user_count

    @patch('services.billing.stripe.checkout.Session.create')
    def test_create_checkout_session_creates_with_correct_args_and_returns_id(
        self,
        create_checkout_session_mock
    ):
        owner = OwnerFactory()
        expected_id = "fkkgosd"
        create_checkout_session_mock.return_value = {"id": expected_id} # only field relevant to implementation
        desired_quantity = 25
        desired_plan = {
            "value": "users-inappm",
            "quantity": desired_quantity
        }

        assert self.stripe.create_checkout_session(owner, desired_plan) == expected_id

        create_checkout_session_mock.assert_called_once_with(
            billing_address_collection="required",
            payment_method_types=["card"],
            client_reference_id=owner.ownerid,
            customer=owner.stripe_customer_id,
            customer_email=owner.email,
            success_url=settings.CLIENT_PLAN_CHANGE_SUCCESS_URL,
            cancel_url=settings.CLIENT_PLAN_CHANGE_CANCEL_URL,
            subscription_data={
                "items": [{
                    "plan": settings.STRIPE_PLAN_IDS[desired_plan["value"]],
                    "quantity": desired_quantity
                }],
                "payment_behavior": "allow_incomplete",
                "metadata": {
                    "service": owner.service,
                    "obo_organization": owner.ownerid,
                    "username": owner.username,
                    "obo_name": self.user.name,
                    "obo_email": self.user.email,
                    "obo": self.user.ownerid
                }
            }
        )


class MockPaymentService(AbstractPaymentService):
    def list_invoices(self, owner, limit=10):
        return f"{owner.ownerid} {limit}"

    def delete_subscription(self, owner):
        pass

    def modify_subscription(self, owner, plan):
        pass

    def create_checkout_session(self, owner, plan):
        pass


class BillingServiceTests(TestCase):
    def setUp(self):
        self.mock_payment_service = MockPaymentService()
        self.billing_service = BillingService(payment_service=self.mock_payment_service)

    def test_default_payment_service_is_stripe(self):
        requesting_user = OwnerFactory()
        assert isinstance(BillingService(requesting_user=requesting_user).payment_service, StripeService)

    def test_list_invoices_calls_payment_service_list_invoices_with_limit(self):
        owner = OwnerFactory()
        assert self.billing_service.list_invoices(owner) == self.mock_payment_service.list_invoices(owner)

    @patch('services.tests.test_billing.MockPaymentService.delete_subscription')
    def test_update_plan_to_users_free_deletes_subscription_if_user_has_stripe_subscription(
        self,
        delete_subscription_mock
    ):
        owner = OwnerFactory(stripe_subscription_id="tor_dsoe")
        self.billing_service.update_plan(owner, {"value": "users-free"})
        delete_subscription_mock.assert_called_once_with(owner)

    @patch('codecov_auth.models.Owner.set_free_plan')
    @patch('services.tests.test_billing.MockPaymentService.create_checkout_session')
    @patch('services.tests.test_billing.MockPaymentService.modify_subscription')
    @patch('services.tests.test_billing.MockPaymentService.delete_subscription')
    def test_update_plan_to_users_free_sets_plan_if_no_subscription_id(
        self,
        delete_subscription_mock,
        modify_subscription_mock,
        create_checkout_session_mock,
        set_free_plan_mock
    ):
        owner = OwnerFactory()
        self.billing_service.update_plan(owner, {"value": "users-free"})

        set_free_plan_mock.assert_called_once()

        delete_subscription_mock.assert_not_called()
        modify_subscription_mock.assert_not_called()
        create_checkout_session_mock.assert_not_called()

    @patch('codecov_auth.models.Owner.set_free_plan')
    @patch('services.tests.test_billing.MockPaymentService.create_checkout_session')
    @patch('services.tests.test_billing.MockPaymentService.modify_subscription')
    @patch('services.tests.test_billing.MockPaymentService.delete_subscription')
    def test_update_plan_modifies_subscription_if_user_plan_and_subscription_exists(
        self,
        delete_subscription_mock,
        modify_subscription_mock,
        create_checkout_session_mock,
        set_free_plan_mock
    ):
        owner = OwnerFactory(stripe_subscription_id=10)
        desired_plan = {
            "value": "users-inappy",
            "quantity": 10
        }
        self.billing_service.update_plan(owner, desired_plan)

        modify_subscription_mock.assert_called_once_with(owner, desired_plan)

        set_free_plan_mock.assert_not_called()
        delete_subscription_mock.assert_not_called()
        create_checkout_session_mock.assert_not_called()

    @patch('codecov_auth.models.Owner.set_free_plan')
    @patch('services.tests.test_billing.MockPaymentService.create_checkout_session')
    @patch('services.tests.test_billing.MockPaymentService.modify_subscription')
    @patch('services.tests.test_billing.MockPaymentService.delete_subscription')
    def test_update_plan_creates_checkout_session_if_user_plan_and_no_subscription(
        self,
        delete_subscription_mock,
        modify_subscription_mock,
        create_checkout_session_mock,
        set_free_plan_mock
    ):
        owner = OwnerFactory(stripe_subscription_id=None)
        desired_plan = {
            "value": "users-inappy",
            "quantity": 10
        }
        self.billing_service.update_plan(owner, desired_plan)

        create_checkout_session_mock.assert_called_once_with(owner, desired_plan)

        set_free_plan_mock.assert_not_called()
        delete_subscription_mock.assert_not_called()
        modify_subscription_mock.assert_not_called()

    @patch('codecov_auth.models.Owner.set_free_plan')
    @patch('services.tests.test_billing.MockPaymentService.create_checkout_session')
    @patch('services.tests.test_billing.MockPaymentService.modify_subscription')
    @patch('services.tests.test_billing.MockPaymentService.delete_subscription')
    def test_update_plan_does_nothing_if_not_switching_to_user_plan(
        self,
        delete_subscription_mock,
        modify_subscription_mock,
        create_checkout_session_mock,
        set_free_plan_mock
    ):
        owner = OwnerFactory()
        desired_plan = {
            "value": "v4-50m"
        }
        self.billing_service.update_plan(owner, desired_plan)

        set_free_plan_mock.assert_not_called()
        delete_subscription_mock.assert_not_called()
        modify_subscription_mock.assert_not_called()
        create_checkout_session_mock.assert_not_called()