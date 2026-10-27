-- Example questions the three tables can answer. Run AFTER 01 and 02.
-- You can run each query on its own in the Neon SQL editor.

-- Show times in Indian Standard Time (the data itself is stored correctly either way).
SET TIME ZONE 'Asia/Kolkata';

-- 1) "I am in Mumbai and need to reach Delhi by the morning of 22 October. What are my options?"
--    (scheduled flights from Mumbai to Delhi that arrive by 12:00 on 22 Oct)
SELECT f.flight_number,
       f.flight_type,
       COALESCE(c.name, f.carrier_name) AS operator,
       f.departure_time,
       f.arrival_time,
       f.aircraft_type,
       f.seats_available,
       f.price_inr,
       f.price_basis
FROM flights f
JOIN airports da ON da.id = f.departure_airport_id
JOIN cities   dc ON dc.id = da.city_id
JOIN airports aa ON aa.id = f.arrival_airport_id
JOIN cities   ac ON ac.id = aa.city_id
LEFT JOIN companies c ON c.id = f.company_id
WHERE dc.name = 'Mumbai'
  AND ac.name = 'Delhi'
  AND f.status = 'scheduled'
  AND f.arrival_time <= '2026-10-22 12:00+05:30'
ORDER BY f.arrival_time;

-- 2) "Which of our companies fly private flights out of Mumbai, and how do I reach them?"
SELECT DISTINCT c.name, c.website, c.phone, c.email
FROM flights f
JOIN airports da ON da.id = f.departure_airport_id
JOIN cities   dc ON dc.id = da.city_id
JOIN companies c ON c.id = f.company_id
WHERE dc.name = 'Mumbai'
  AND f.flight_type = 'private_charter'
  AND f.status = 'scheduled'
ORDER BY c.name;

-- 3) Every flight in plain words
SELECT f.flight_number,
       f.flight_type,
       COALESCE(c.name, f.carrier_name) AS operator,
       dc.name AS from_city,
       ac.name AS to_city,
       f.departure_time,
       f.arrival_time,
       f.seats_available,
       f.status
FROM flights f
JOIN airports da ON da.id = f.departure_airport_id
JOIN cities   dc ON dc.id = da.city_id
JOIN airports aa ON aa.id = f.arrival_airport_id
JOIN cities   ac ON ac.id = aa.city_id
LEFT JOIN companies c ON c.id = f.company_id
ORDER BY f.departure_time;

-- 4) How many flights of each kind, and in which state
SELECT flight_type, status, count(*) AS flights
FROM flights
GROUP BY flight_type, status
ORDER BY flight_type, status;
