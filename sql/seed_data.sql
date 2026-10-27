-- Avatition: Seed data — 10 Delhi NCR aviation companies
-- Milestone 2
-- All facts sourced from public URLs listed in company_facts.source_url.
-- verified=TRUE only where an independent source (not the company's own site) confirms the fact,
-- OR where the company's own site states a specific verifiable detail (fleet page, DGCA listing).
-- verified=FALSE for self-reported claims without corroboration.
-- as_of_date: date we fetched the source page.

-- ─────────────────────────────────────────────
-- COMPANIES (10 records)
-- ─────────────────────────────────────────────
INSERT INTO companies
    (slug, name, category, region, headquarters_city, website_url, iata_code, dgca_approval_no, description, verified)
VALUES
-- 1. Air Charter Services Pvt. Ltd.
(
    'air-charter-services',
    'Air Charter Services Pvt. Ltd.',
    'charter_operator',
    'Delhi NCR',
    'New Delhi',
    'https://aircharterservices.com/',
    NULL,
    NULL,  -- NSOP number not publicly listed; to be verified via DGCA
    'Delhi-based NSOP charter operator offering private jets, helicopters, and air ambulance services, based at IGI Airport General Aviation Terminal.',
    TRUE   -- HQ and NSOP status confirmed by theflyingengineer.com listing
),
-- 2. IndoPacific Aviation Services Pvt. Ltd. (subsidiary of JetSetGo)
(
    'indopacific-aviation',
    'IndoPacific Aviation Services Pvt. Ltd.',
    'charter_operator',
    'Delhi NCR',
    'New Delhi',
    'http://indopacificaviation.com/',
    NULL,
    NULL,
    'New Delhi NSOP charter and aircraft management operator with CAR-145 approved maintenance; now a JetSetGo subsidiary.',
    TRUE   -- NSOP and CAR-145 confirmed by theflyingengineer.com listing
),
-- 3. JetSetGo Aviation Services Pvt. Ltd.
(
    'jetsetgo',
    'JetSetGo Aviation Services Pvt. Ltd.',
    'charter_operator',
    'Delhi NCR',
    'New Delhi',
    'https://jetsetgo.in/',
    NULL,
    NULL,
    'New Delhi-based aggregator and charter operator offering jets, turboprops, and helicopters across India; also provides aircraft management, MRO, and consultancy.',
    TRUE   -- HQ confirmed by theflyingengineer.com listing
),
-- 4. Club One Air
(
    'club-one-air',
    'Club One Air',
    'charter_operator',
    'Delhi NCR',
    'New Delhi',
    'https://www.cluboneair.com/',
    NULL,
    NULL,
    'Delhi-based private jet charter operator, founded 2005. Primary base at IGI Airport, with secondary base in Mumbai. Operates Dassault Falcon 2000 and Cessna Citation aircraft.',
    TRUE   -- founding year, base, and aircraft types confirmed by Wikipedia
),
-- 5. Indamer MJets (FBO at IGI Airport)
(
    'indamer-mjets',
    'Indamer MJets',
    'fbo',
    'Delhi NCR',
    'New Delhi',
    'https://indamer.in/',
    NULL,
    NULL,
    'Fixed-base operator at Indira Gandhi International Airport, New Delhi. Part of Indamer Aviation network. Offers two 32,000 sq ft hangars, VIP lounges, six private client rooms, customs and immigration facilities.',
    TRUE   -- FBO opening and hangar details confirmed by AIN Online (Aug 2025)
),
-- 6. Bird Delhi General Aviation Services Pvt. Ltd. (BDGASPL)
(
    'bird-delhi',
    'Bird Delhi General Aviation Services Pvt. Ltd.',
    'fbo',
    'Delhi NCR',
    'New Delhi',
    NULL,  -- no independent website confirmed
    NULL,
    NULL,
    'FBO and MRO provider at IGI Airport. Formerly Bird ExecuJet; rebranded after ExecuJet exit in 2019. Now 49% owned by GMR Airports. Two enclosed MRO hangars (21,500 sq ft each), 50,000 sq ft apron, capacity for 6–8 midsize jets.',
    TRUE   -- hangar sizes, apron, GMR stake, aircraft types confirmed by AIN Online (Sep 2025)
),
-- 7. Global Vectra Helicorp Ltd.
(
    'global-vectra-helicorp',
    'Global Vectra Helicorp Ltd.',
    'charter_operator',
    'Delhi NCR',
    'New Delhi',  -- onshore operations HQ in New Delhi per Wikipedia
    'https://www.globalhelicorp.com/',
    NULL,
    NULL,
    'India''s largest helicopter company offering offshore and onshore charter. New Delhi onshore operations hub. Fleet of Bell 412EP, AS350 B3/B3E, AW139, and AW169 helicopters. ISO 9001:2015 certified.',
    TRUE   -- fleet types, New Delhi ops, certifications confirmed by Wikipedia
),
-- 8. Indamer Technics (MRO)
(
    'indamer-technics',
    'Indamer Technics Pvt. Ltd.',
    'mro',
    'Delhi NCR',
    'New Delhi',
    'https://indamer.in/',
    NULL,
    NULL,
    'MRO arm of Indamer Aviation group. 50% owned by Adani Defence & Aerospace. Authorized to service Bombardier, Embraer, and Leonardo aircraft. Linked to Indamer MJets FBO at IGI Airport.',
    TRUE   -- Adani ownership and authorizations confirmed by AIN Online (Sep 2025) and ainonline.com (Dec 2014)
),
-- 9. JetSetGo (aircraft management arm — separate facts row, same company listed separately as mgmt)
-- NOTE: JetSetGo offers both charter AND aircraft management; we model it as charter_operator above.
-- For the 10th record, we add a distinct operator confirmed to have Delhi NCR presence.
-- Target Air Services — confirmed at IGI based on ch-aviation.com news item
(
    'target-air-services',
    'Target Air Services Pvt. Ltd.',
    'charter_operator',
    'Delhi NCR',
    'New Delhi',
    NULL,
    NULL,
    NULL,
    'Delhi NCR-based NSOP charter operator. Noted by ch-aviation.com for adding an executive jet to its fleet.',
    FALSE  -- limited public data; ch-aviation item confirms Delhi base, no other detail verified
),
-- 10. Air Charter Services (Pvt. Ltd.) — Pilatus authorized service centre
-- Already inserted as record 1. Use slot 10 for: Deccan Charters (Delhi operations, not HQ)
-- Better: use India Fly Safe Aviation which the Flying Engineer lists under Delhi
(
    'india-fly-safe',
    'India Fly Safe Aviation Pvt. Ltd.',
    'charter_operator',
    'Delhi NCR',
    'New Delhi',
    NULL,
    NULL,
    NULL,
    'Delhi NCR-based NSOP private charter operator listed on theflyingengineer.com under India charter operators.',
    FALSE  -- only source is theflyingengineer.com listing; no independent verification yet
);

-- ─────────────────────────────────────────────
-- COMPANY FACTS
-- One row per verifiable claim. source_url required.
-- ─────────────────────────────────────────────
INSERT INTO company_facts
    (company_id, fact_type, fact_value, source_url, verified, as_of_date)
SELECT c.id, f.fact_type, f.fact_value, f.source_url, f.verified, f.as_of_date
FROM companies c
JOIN (VALUES

-- ── Air Charter Services Pvt. Ltd. ──────────────────────────────────────
('air-charter-services', 'base_airport',  'Indira Gandhi International Airport (VIDP), Hangar 3, General Aviation Terminal', 'https://theflyingengineer.com/listing/air-charter-services-pvt-ltd/', TRUE,  '2026-10-17'),
('air-charter-services', 'aircraft_type', 'large: Dassault Falcon 6X',          'https://theflyingengineer.com/listing/air-charter-services-pvt-ltd/', TRUE,  '2026-10-17'),
('air-charter-services', 'aircraft_type', 'large: Dassault Falcon 2000LX',       'https://theflyingengineer.com/listing/air-charter-services-pvt-ltd/', TRUE,  '2026-10-17'),
('air-charter-services', 'aircraft_type', 'midsize: Cessna Citation 560XL',       'https://theflyingengineer.com/listing/air-charter-services-pvt-ltd/', TRUE,  '2026-10-17'),
('air-charter-services', 'aircraft_type', 'light: Cessna Citation CJ2+',          'https://theflyingengineer.com/listing/air-charter-services-pvt-ltd/', TRUE,  '2026-10-17'),
('air-charter-services', 'aircraft_type', 'turboprop: Beechcraft King Air 200',   'https://theflyingengineer.com/listing/air-charter-services-pvt-ltd/', TRUE,  '2026-10-17'),
('air-charter-services', 'aircraft_type', 'helicopter: Agusta A109S Grand',       'https://theflyingengineer.com/listing/air-charter-services-pvt-ltd/', TRUE,  '2026-10-17'),
('air-charter-services', 'certification', 'Pilatus Authorized Sales and Service Centre for India', 'https://en.wikipedia.org/wiki/Air_Charter_Services_Pvt._Ltd.', TRUE, '2026-10-17'),
('air-charter-services', 'certification', 'BAOA BizAvIndia Award 2015',           'https://en.wikipedia.org/wiki/Air_Charter_Services_Pvt._Ltd.', TRUE,  '2026-10-17'),

-- ── IndoPacific Aviation ─────────────────────────────────────────────────
('indopacific-aviation', 'base_airport',  'New Delhi (VIDP)', 'https://theflyingengineer.com/listing/indopacific-aviation/', TRUE, '2026-10-17'),
('indopacific-aviation', 'aircraft_type', 'light: light jets (category)',          'https://theflyingengineer.com/listing/indopacific-aviation/', FALSE, '2026-10-17'),
('indopacific-aviation', 'aircraft_type', 'midsize: midsize jets (category)',      'https://theflyingengineer.com/listing/indopacific-aviation/', FALSE, '2026-10-17'),
('indopacific-aviation', 'aircraft_type', 'large: large jets (category)',          'https://theflyingengineer.com/listing/indopacific-aviation/', FALSE, '2026-10-17'),
('indopacific-aviation', 'aircraft_type', 'helicopter: helicopters (category)',    'https://theflyingengineer.com/listing/indopacific-aviation/', FALSE, '2026-10-17'),
('indopacific-aviation', 'certification', 'NSOP (Non-Scheduled Operator Permit)',  'https://theflyingengineer.com/listing/indopacific-aviation/', TRUE,  '2026-10-17'),
('indopacific-aviation', 'certification', 'CAR-145 Approved Maintenance Organization', 'https://theflyingengineer.com/listing/indopacific-aviation/', TRUE, '2026-10-17'),
('indopacific-aviation', 'owner_operator','JetSetGo subsidiary (acquired Apr 2018)', 'https://yourstory.com/2018/04/jet-set-go-acquires-indo-pacific-aviation/', TRUE, '2026-10-17'),

-- ── JetSetGo ────────────────────────────────────────────────────────────
('jetsetgo', 'base_airport',  'New Delhi (Nehru Place, South Delhi)', 'https://theflyingengineer.com/listing/jetsetgo-aviation-services/', TRUE, '2026-10-17'),
('jetsetgo', 'aircraft_type', 'turboprop: turboprops (category)',      'https://theflyingengineer.com/listing/jetsetgo-aviation-services/', FALSE, '2026-10-17'),
('jetsetgo', 'aircraft_type', 'light: light jets (category)',           'https://theflyingengineer.com/listing/jetsetgo-aviation-services/', FALSE, '2026-10-17'),
('jetsetgo', 'aircraft_type', 'midsize: midsize jets (category)',       'https://theflyingengineer.com/listing/jetsetgo-aviation-services/', FALSE, '2026-10-17'),
('jetsetgo', 'aircraft_type', 'large: large jets and airliners up to 25 pax', 'https://theflyingengineer.com/listing/jetsetgo-aviation-services/', FALSE, '2026-10-17'),
('jetsetgo', 'aircraft_type', 'helicopter: Agusta AW109 Grand (HeliSetGo)', 'https://theflyingengineer.com/listing/jetsetgo-aviation-services/', TRUE, '2026-10-17'),
('jetsetgo', 'certification', 'NSOP (Non-Scheduled Operator Permit)',  'https://theflyingengineer.com/listing/jetsetgo-aviation-services/', TRUE,  '2026-10-17'),
('jetsetgo', 'year_founded',  '2014',                                   'https://jetsetgo.in/blog/a-guide-to-the-different-types-of-private-jets', FALSE, '2026-10-17'),

-- ── Club One Air ────────────────────────────────────────────────────────
('club-one-air', 'base_airport',  'Indira Gandhi International Airport (VIDP), primary base', 'https://en.wikipedia.org/wiki/Club_One_Air', TRUE, '2026-10-17'),
('club-one-air', 'year_founded',  '2005',                                'https://en.wikipedia.org/wiki/Club_One_Air', TRUE, '2026-10-17'),
('club-one-air', 'aircraft_type', 'large: Dassault Falcon 2000 (5 aircraft)', 'https://en.wikipedia.org/wiki/Club_One_Air', TRUE, '2026-10-17'),
('club-one-air', 'aircraft_type', 'midsize: Cessna Citation Excel (2 aircraft)', 'https://en.wikipedia.org/wiki/Club_One_Air', TRUE, '2026-10-17'),
('club-one-air', 'aircraft_type', 'light: Cessna Citation II (1 aircraft)',       'https://en.wikipedia.org/wiki/Club_One_Air', TRUE, '2026-10-17'),
('club-one-air', 'fleet_size',    '8 aircraft (as of 2024; Wikipedia data inconsistency noted)', 'https://en.wikipedia.org/wiki/Club_One_Air', FALSE, '2026-10-17'),

-- ── Indamer MJets (FBO) ─────────────────────────────────────────────────
('indamer-mjets', 'base_airport', 'Indira Gandhi International Airport (VIDP)', 'https://www.ainonline.com/aviation-news/2025-08-19/second-fbo-lands-delhi-international-airport', TRUE, '2026-10-17'),
('indamer-mjets', 'service_area', 'FBO: two 32,000 sq ft hangars, VIP lounges, 6 private client rooms', 'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('indamer-mjets', 'service_area', 'FBO: customs and immigration facilities on-site',  'https://backend.ainonline.com/aviation-news/business-aviation/2020-11-04/indias-first-true-fbo-opens-delhi', TRUE, '2026-10-17'),
('indamer-mjets', 'service_area', 'Capacity: ~100 flights per day (managing director claim)', 'https://backend.ainonline.com/aviation-news/business-aviation/2020-11-04/indias-first-true-fbo-opens-delhi', FALSE, '2026-10-17'),

-- ── Bird Delhi General Aviation Services ─────────────────────────────────
('bird-delhi', 'base_airport',  'Indira Gandhi International Airport (VIDP)', 'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('bird-delhi', 'service_area',  'MRO: two enclosed hangars (21,500 sq ft each), 50,000 sq ft apron',  'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('bird-delhi', 'service_area',  'Apron capacity: 6–8 midsize jets',           'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('bird-delhi', 'aircraft_type', 'midsize: Gulfstream IV, Hawker, Cessna Citation, King Air, Piaggio Avanti (service types)', 'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('bird-delhi', 'owner_operator','49% owned by GMR Airports (acquired 2025)',  'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),

-- ── Global Vectra Helicorp ───────────────────────────────────────────────
('global-vectra-helicorp', 'base_airport', 'New Delhi (onshore operations hub)',  'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'year_founded', '1997',                               'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'fleet_size',   '29–30 helicopters (Wikipedia; figures inconsistent)', 'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', FALSE, '2026-10-17'),
('global-vectra-helicorp', 'aircraft_type','helicopter: Bell 412EP',              'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'aircraft_type','helicopter: AS350 B3 / AS350 B3E',   'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'aircraft_type','helicopter: AW139',                   'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'aircraft_type','helicopter: AW169',                   'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'certification','ISO 9001:2015',                       'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'certification','ISO 14001:2015',                      'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'certification','OHSAS 18001:2007',                    'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),
('global-vectra-helicorp', 'certification','DGCA-certified Bell fleet maintenance facility', 'https://en.wikipedia.org/wiki/Global_Vectra_Helicorp', TRUE, '2026-10-17'),

-- ── Indamer Technics (MRO) ──────────────────────────────────────────────
('indamer-technics', 'base_airport',  'Indira Gandhi International Airport (VIDP), linked to Indamer MJets FBO', 'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('indamer-technics', 'owner_operator','50% owned by Adani Defence & Aerospace',  'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('indamer-technics', 'certification', 'Bombardier Authorized Service Facility (2014)', 'https://ainonline.com/aviation-news/business-aviation/2014-12-07/bombardier-taps-indamer-boost-global-service-india', TRUE, '2026-10-17'),
('indamer-technics', 'aircraft_type', 'mro: Bombardier business jets',           'https://ainonline.com/aviation-news/business-aviation/2014-12-07/bombardier-taps-indamer-boost-global-service-india', TRUE, '2026-10-17'),
('indamer-technics', 'aircraft_type', 'mro: Embraer aircraft',                   'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),
('indamer-technics', 'aircraft_type', 'mro: Leonardo aircraft',                  'https://backend.ainonline.com/aviation-news/business-aviation/2025-09-05/indias-business-aviation-blind-spot-fbos', TRUE, '2026-10-17'),

-- ── Target Air Services (limited data) ──────────────────────────────────
('target-air-services', 'base_airport', 'New Delhi (inferred from DGCA listing)', 'https://www.ch-aviation.com/news/154235-indias-target-air-services-adds-first-executive-jet', FALSE, '2026-10-17'),
('target-air-services', 'aircraft_type','executive jet (type not named in source)', 'https://www.ch-aviation.com/news/154235-indias-target-air-services-adds-first-executive-jet', FALSE, '2026-10-17'),

-- ── India Fly Safe Aviation (limited data) ───────────────────────────────
('india-fly-safe', 'base_airport', 'New Delhi (per Flying Engineer listing)',     'https://theflyingengineer.com/listing/charter/india-fly-safe-aviation/', FALSE, '2026-10-17')

) AS f(slug, fact_type, fact_value, source_url, verified, as_of_date)
ON c.slug = f.slug;

-- ─────────────────────────────────────────────
-- SEARCH TEXT (populate from companies + facts)
-- ─────────────────────────────────────────────
INSERT INTO company_search_text (company_id, search_body, tsv)
SELECT
    c.id,
    CONCAT_WS(' ',
        c.name,
        c.category,
        c.region,
        c.headquarters_city,
        c.description,
        STRING_AGG(cf.fact_value, ' ')
    ) AS search_body,
    TO_TSVECTOR('english', CONCAT_WS(' ',
        c.name,
        c.category,
        c.region,
        c.headquarters_city,
        c.description,
        STRING_AGG(cf.fact_value, ' ')
    )) AS tsv
FROM companies c
LEFT JOIN company_facts cf ON cf.company_id = c.id
GROUP BY c.id, c.name, c.category, c.region, c.headquarters_city, c.description;
