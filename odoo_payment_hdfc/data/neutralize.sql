-- disable hdfc payment provider
UPDATE payment_provider
   SET hdfc_merchant_id = NULL,
       hdfc_merchant_name = NULL,
       hdfc_merchant_key = NULL,
       hdfc_merchant_vpa = NULL;
