create table if not exists news_items (
  id uuid primary key default gen_random_uuid(),
  source text,
  title_original text,
  title_ru text,
  url text unique not null,
  published_at timestamptz,
  category text,
  importance text,
  summary_ru text,
  post_text_ru text,
  image_prompt text,
  status text default 'collected',
  telegram_message_id text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists daily_summaries (
  id uuid primary key default gen_random_uuid(),
  summary_date date unique,
  text_ru text,
  telegram_message_id text,
  created_at timestamptz default now()
);

create table if not exists weekly_summaries (
  id uuid primary key default gen_random_uuid(),
  week_start date,
  week_end date,
  text_ru text,
  telegram_message_id text,
  created_at timestamptz default now()
);
