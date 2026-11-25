-- WRONG: a payment with two complaints and three events appears SIX times.
-- This overstates payment value and should never be used for a financial KPI.
SELECT SUM(p.amount_paise)/100.0 AS WRONG_total_inr
FROM payments p
JOIN complaints c ON c.payment_id=p.payment_id
JOIN payment_events e ON e.payment_id=p.payment_id;

-- CORRECT: isolate the qualifying payment IDs, then SUM each payment once.
SELECT SUM(p.amount_paise)/100.0 AS correct_total_inr
FROM payments p
WHERE EXISTS (SELECT 1 FROM complaints c WHERE c.payment_id=p.payment_id)
  AND EXISTS (SELECT 1 FROM payment_events e WHERE e.payment_id=p.payment_id);
