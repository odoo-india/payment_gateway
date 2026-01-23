-- disable billdesk payment provider
UPDATE payment_provider
   SET billdesk_merchant_id = NULL,
       billdesk_client_id = NULL,
       billdesk_key_id = NULL,
       billdesk_encryption_key = NULL,
       billdesk_signing_key = NULL;
