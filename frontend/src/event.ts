
export type Event = {
  event_id: string,
  source_name: string,
  base_url?: string,
  source_url: string,
  image_url?: string,
  event_title: string,
  start_date: string,
  start_time?: string | null,
  end_datetime?: string | null,
  location: string,
  description: string,
  extracted_at: string,
  ai_updated?: boolean | null,
  ai_updated_at?: string | null,
}
