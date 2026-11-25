-- Grain: ONE input row per payment in payments.
-- Contact counts collapsed to ONE row per payment before joining.
-- Denominator: count of successful payments in each payment-month cohort.
-- Mature cutoff: 45 days before 2026-11-25 (fixed snapshot).
WITH contacts AS (
  SELECT c.payment_id, COUNT(*) AS contact_count
  FROM complaints c JOIN payments p ON p.payment_id=c.payment_id
  WHERE DATETIME(c.created_at) BETWEEN DATETIME(p.created_at) AND DATETIME(p.created_at,'+45 days') AND DATE(c.created_at)<=DATE('2026-11-25') GROUP BY c.payment_id
), payment_grain AS (
  SELECT strftime('%Y-%m',p.created_at) AS cohort,
         p.payment_id,p.member_id,p.status,p.amount_paise,
         COALESCE(c.contact_count,0) AS contact_count,
         CASE WHEN c.payment_id IS NOT NULL THEN 1 ELSE 0 END AS disputed
  FROM payments p LEFT JOIN contacts c ON c.payment_id=p.payment_id
  WHERE DATE(p.created_at) <= DATE('2026-11-25','-45 days')
)
SELECT cohort, COUNT(*) AS payments,
       SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS successes,
       SUM(contact_count) AS tickets,
       SUM(disputed) AS unique_disputed_payments,
       COUNT(DISTINCT CASE WHEN disputed=1 THEN member_id END) AS affected_members,
       ROUND(1000.0*SUM(contact_count)/NULLIF(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),0),2) AS contacts_per_1000_successes
FROM payment_grain GROUP BY cohort ORDER BY cohort;
