create table if not exists public.users (
  id bigint generated always as identity primary key,
  username text not null unique,
  password_hash text not null,
  created_at text not null
);

create table if not exists public.decisions (
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  mode text not null,
  title text not null,
  category text not null,
  decision_text text not null,
  score numeric not null,
  recommendation text not null,
  inputs_json text,
  penalties_json text,
  notes text,
  tags text,
  review_due_at text,
  outcome_status text,
  outcome_quality integer,
  outcome_notes text,
  confidence_user numeric,
  confidence_system numeric,
  confidence_gap numeric,
  created_at text not null
);

create index if not exists decisions_user_id_idx on public.decisions(user_id);
create index if not exists decisions_review_due_at_idx on public.decisions(review_due_at);
create index if not exists decisions_created_at_idx on public.decisions(created_at);
