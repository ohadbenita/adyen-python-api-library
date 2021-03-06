import Adyen
import unittest
from BaseTest import BaseTest

class TestBinLookup(unittest.TestCase):
    ady = Adyen.Adyen()

    client = ady.client
    test = BaseTest(ady)
    client.username = "YourWSUser"
    client.password = "YourWSPassword"
    client.platform = "test"
    client.app_name = "appname"

    def test_get_cost_estimate_success(self):
        request = {'merchantAccount': 'YourMerchantAccount', 'amount': '1000'}
        expected = {'cardBin': {'bin': '458012', 'commercial': False, 'fundingSource': 'CHARGE',
                                'fundsAvailability': 'N', 'issuingBank': 'Bank Of America',
                                'issuingCountry': 'US', 'issuingCurrency': 'USD',
                                'paymentMethod': 'Y',
                                'summary': '6789'},
                    'costEstimateAmount': {'currency': 'USD', 'value': 1234},
                    'resultCode': 'Success', 'surchargeType': 'PASSTHROUGH'}

        self.ady.client = self.test.create_client_from_file(200, request,
                                                            'test/mocks/binlookup/'
                                                            'getcostestimate-success'
                                                            '.json')
        result = self.ady.binlookup.get_cost_estimate(request)
        self.assertEqual(expected, result.message)

TestBinLookup.client.http_force = "requests"
suite = unittest.TestLoader().loadTestsFromTestCase(TestBinLookup)
unittest.TextTestRunner(verbosity=2).run(suite)
TestBinLookup.client.http_force = "pycurl"
TestBinLookup.client.http_init = False
suite = unittest.TestLoader().loadTestsFromTestCase(TestBinLookup)
unittest.TextTestRunner(verbosity=2).run(suite)
TestBinLookup.client.http_force = "other"
TestBinLookup.client.http_init = False
suite = unittest.TestLoader().loadTestsFromTestCase(TestBinLookup)
unittest.TextTestRunner(verbosity=2).run(suite)
