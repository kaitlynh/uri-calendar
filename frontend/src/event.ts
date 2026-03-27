
export type Event = {
  event_id: string,
  source_name: string,
  source_url: string,
  event_title: string,
  start_date: string,
  start_time: string,
  end_datetime?: string,
  location: string,
  description: string,
  extracted_at: string
}
