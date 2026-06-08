CREATE TABLE IF NOT EXISTS companies (
    cik VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    name VARCHAR,
    exchange VARCHAR,
    sic VARCHAR,
    sic_description VARCHAR,
    fiscal_year_end VARCHAR,
    entity_type VARCHAR,
    last_refreshed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS filings (
    cik VARCHAR,
    accession_number VARCHAR,
    form VARCHAR,
    filing_date DATE,
    report_date DATE,
    acceptance_datetime VARCHAR,
    primary_document VARCHAR,
    primary_doc_description VARCHAR,
    is_inline_xbrl BOOLEAN,
    source_url VARCHAR,
    PRIMARY KEY (cik, accession_number)
);

CREATE TABLE IF NOT EXISTS raw_companyfacts (
    cik VARCHAR,
    retrieved_at TIMESTAMP,
    source_url VARCHAR,
    json_blob JSON,
    content_hash VARCHAR,
    PRIMARY KEY (cik, content_hash)
);

CREATE TABLE IF NOT EXISTS facts (
    cik VARCHAR,
    taxonomy VARCHAR,
    tag VARCHAR,
    label VARCHAR,
    description VARCHAR,
    unit VARCHAR,
    value DOUBLE,
    start_date DATE,
    end_date DATE,
    fiscal_year INTEGER,
    fiscal_period VARCHAR,
    form VARCHAR,
    accession_number VARCHAR,
    filed_date DATE,
    frame VARCHAR,
    source_hash VARCHAR
);

CREATE TABLE IF NOT EXISTS statement_items (
    cik VARCHAR,
    statement VARCHAR,
    canonical_item VARCHAR,
    taxonomy VARCHAR,
    tag VARCHAR,
    unit VARCHAR,
    value DOUBLE,
    period_end DATE,
    fiscal_year INTEGER,
    fiscal_period VARCHAR,
    form VARCHAR,
    accession_number VARCHAR,
    confidence DOUBLE,
    quality_flag VARCHAR
);

CREATE TABLE IF NOT EXISTS ratios (
    cik VARCHAR,
    ratio_category VARCHAR,
    ratio_name VARCHAR,
    value DOUBLE,
    numerator DOUBLE,
    denominator DOUBLE,
    period_end DATE,
    fiscal_year INTEGER,
    fiscal_period VARCHAR,
    form VARCHAR,
    accession_number VARCHAR,
    formula_version VARCHAR,
    quality_flag VARCHAR
);

CREATE TABLE IF NOT EXISTS ratio_components (
    cik VARCHAR,
    ratio_name VARCHAR,
    period_end DATE,
    component_name VARCHAR,
    canonical_item VARCHAR,
    taxonomy VARCHAR,
    tag VARCHAR,
    value DOUBLE,
    unit VARCHAR,
    accession_number VARCHAR
);

CREATE TABLE IF NOT EXISTS management_discussions (
    cik VARCHAR,
    accession_number VARCHAR,
    form VARCHAR,
    filing_date DATE,
    report_date DATE,
    section_title VARCHAR,
    discussion_text VARCHAR,
    summary VARCHAR,
    sentiment_label VARCHAR,
    sentiment_score DOUBLE,
    positive_terms INTEGER,
    negative_terms INTEGER,
    word_count INTEGER,
    source_url VARCHAR,
    extracted_at TIMESTAMP,
    PRIMARY KEY (cik, accession_number)
);

CREATE TABLE IF NOT EXISTS analysis_notes (
    id VARCHAR PRIMARY KEY,
    cik VARCHAR,
    ticker VARCHAR,
    scope VARCHAR,
    period_end DATE,
    title VARCHAR,
    body_markdown VARCHAR,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
