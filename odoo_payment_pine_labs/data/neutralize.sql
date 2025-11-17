-- disable phonepe payment provider
UPDATE payment_provider
   SET pine_labs_client_id = NULL,
       pine_labs_client_secret = NULL,
       pine_labs_access_token = NULL,
       pine_labs_access_token_expiry = NULL
