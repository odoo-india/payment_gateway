-- disable ccavenue payment provider
UPDATE payment_provider
   SET ccavenue_merchant_id = NULL,
       ccavenue_access_code = NULL,
       ccavenue_working_key = NULL;
