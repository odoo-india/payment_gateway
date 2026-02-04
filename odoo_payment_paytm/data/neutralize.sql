-- disable paytm payment provider
UPDATE payment_provider
   SET paytm_merchant_id = NULL,
       paytm_merchant_key = NULL;
