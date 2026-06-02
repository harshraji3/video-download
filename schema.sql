create extension if not exists "pgcrypto";

-- ============================================================
-- Documents
-- ============================================================
create table documents (
  id          uuid primary key default gen_random_uuid(),
  url         text not null,
  title       text,
  authors     text[],
  publication_source text,
  publication_date   date,
  doi         text,
  source_type text not null default 'web_article',
  crawled_at  timestamptz,
  metadata    jsonb default '{}',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create unique index idx_documents_url on documents (url);

-- ============================================================
-- Paragraphs
-- ============================================================
create table paragraphs (
  id          uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  idx         int not null,           -- position within the document
  content     text not null,
  heading     text,                    -- section heading this paragraph belongs to
  char_count  int generated always as (length(content)) stored,
  created_at  timestamptz not null default now()
);

create index idx_paragraphs_document_id on paragraphs (document_id);
create unique index idx_paragraphs_doc_idx on paragraphs (document_id, idx);

-- ============================================================
-- Sentences
-- ============================================================
create table sentences (
  id           uuid primary key default gen_random_uuid(),
  paragraph_id uuid not null references paragraphs(id) on delete cascade,
  idx          int not null,           -- position within the paragraph
  content      text not null,
  char_count   int generated always as (length(content)) stored,
  created_at   timestamptz not null default now()
);

create index idx_sentences_paragraph_id on sentences (paragraph_id);
create unique index idx_sentences_para_idx on sentences (paragraph_id, idx);

-- ============================================================
-- Updated-at trigger (shared by all tables with updated_at)
-- ============================================================
create or replace function trigger_set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger set_updated_at
  before update on documents
  for each row execute function trigger_set_updated_at();
