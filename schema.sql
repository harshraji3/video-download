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
  raw_html    text,
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
  idx         int not null,
  content     text not null,
  heading     text,
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
  document_id  uuid not null references documents(id) on delete cascade,
  doc_idx      int not null,            -- global position within the document
  idx          int not null,            -- position within the paragraph
  content      text not null,
  char_count   int generated always as (length(content)) stored,
  created_at   timestamptz not null default now()
);

create index idx_sentences_paragraph_id on sentences (paragraph_id);
create index idx_sentences_document_id on sentences (document_id);
create index idx_sentences_doc_idx on sentences (document_id, doc_idx);
create unique index idx_sentences_para_idx on sentences (paragraph_id, idx);

-- ============================================================
-- Chunks
-- ============================================================
create table chunks (
  id                uuid primary key default gen_random_uuid(),
  document_id       uuid not null references documents(id) on delete cascade,
  content           text not null,
  sentence_start    int not null,       -- first doc_idx in chunk
  sentence_end      int not null,       -- last doc_idx in chunk
  sentence_ids      uuid[] not null,
  embedding_id      text,               -- id in ChromaDB
  created_at        timestamptz not null default now()
);

create index idx_chunks_document_id on chunks (document_id);

-- ============================================================
-- Audio Files
-- ============================================================
create table audio_files (
  id              uuid primary key default gen_random_uuid(),
  filename        text not null,
  file_path       text not null,
  title           text,
  speaker         text,
  duration_seconds numeric,
  file_size_bytes int,
  mime_type       text not null default 'audio/mpeg',
  metadata        jsonb default '{}',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ============================================================
-- Transcripts
-- ============================================================
create table transcripts (
  id              uuid primary key default gen_random_uuid(),
  audio_file_id   uuid not null references audio_files(id) on delete cascade,
  content         text not null,
  segments        jsonb not null default '[]',
  model_used      text not null default 'whisper',
  created_at      timestamptz not null default now()
);

create index idx_transcripts_audio_file_id on transcripts (audio_file_id);

-- ============================================================
-- Transcript Sentences
-- ============================================================
create table transcript_sentences (
  id              uuid primary key default gen_random_uuid(),
  transcript_id   uuid not null references transcripts(id) on delete cascade,
  audio_file_id   uuid not null references audio_files(id) on delete cascade,
  doc_idx         int not null,
  idx             int not null,
  content         text not null,
  start_time      numeric not null,
  end_time        numeric not null,
  created_at      timestamptz not null default now()
);

create index idx_ts_audio_file_id on transcript_sentences (audio_file_id);
create index idx_ts_audio_doc on transcript_sentences (audio_file_id, doc_idx);

drop index if exists idx_ts_transcript_idx;
drop index if exists idx_ts_doc_idx;
create unique index idx_ts_transcript_doc on transcript_sentences (transcript_id, doc_idx);

-- ============================================================
-- Audio Chunks
-- ============================================================
create table audio_chunks (
  id                uuid primary key default gen_random_uuid(),
  audio_file_id     uuid not null references audio_files(id) on delete cascade,
  content           text not null,
  sentence_start    int not null,
  sentence_end      int not null,
  sentence_ids      uuid[] not null,
  start_time        numeric not null,
  end_time          numeric not null,
  embedding_id      text,
  created_at        timestamptz not null default now()
);

create index idx_audio_chunks_audio_file_id on audio_chunks (audio_file_id);

-- ============================================================
-- Updated-at trigger
-- ============================================================
create or replace function trigger_set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists set_updated_at on documents;
create trigger set_updated_at
  before update on documents
  for each row execute function trigger_set_updated_at();

drop trigger if exists set_updated_at_audio on audio_files;
create trigger set_updated_at_audio
  before update on audio_files
  for each row execute function trigger_set_updated_at();
