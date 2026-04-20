/** Canonical event shape returned by /api/events. Mirrors db/schema.sql. */
export type Event = {
  event_id: string,
  source_name: string,
  base_url?: string,
  source_url: string,
  image_url?: string,
  display_name?: string | null,
  icon_filename?: string | null,
  event_title: string,
  start_date: string,
  start_time?: string | null,
  end_datetime?: string | null,
  location: string,
  description: string,
  extracted_at: string,
  ai_flag?: boolean | null,
  ai_flag_at?: string | null,
}
