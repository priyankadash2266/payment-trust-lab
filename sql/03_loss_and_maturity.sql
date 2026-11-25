-- ONE output row per payment-month; only known net losses available by as-of.
-- Denominator: value of successful payments in the payment cohort.
-- Never equate covered historical losses with savings from an intervention.
SELECT strftime('%Y-%m', p.created_at) AS cohort,
       SUM(CASE WHEN p.status='success' THEN p.amount_paise ELSE 0 END)/100.0 AS successful_value_inr,
       SUM(CASE WHEN o.outcome='confirmed_fraud'
                    AND DATE(o.available_at)<=DATE('2026-11-25') AND DATETIME(o.available_at)<=DATETIME(p.created_at,'+45 days') THEN o.confirmed_net_loss_paise ELSE 0 END)/100.0 AS known_net_loss_inr,
       ROUND(10000.0*SUM(CASE WHEN o.outcome='confirmed_fraud'
                    AND DATE(o.available_at)<=DATE('2026-11-25') AND DATETIME(o.available_at)<=DATETIME(p.created_at,'+45 days') THEN o.confirmed_net_loss_paise ELSE 0 END)
         /NULLIF(SUM(CASE WHEN p.status='success' THEN p.amount_paise ELSE 0 END),0),2) AS known_loss_bps
FROM payments p LEFT JOIN outcomes o ON o.payment_id=p.payment_id
WHERE DATE(p.created_at)<=DATE('2026-11-25','-45 days')
GROUP BY cohort ORDER BY cohort;
