/** Map source_name from the API to local icon filenames */
export const SOURCE_ICON_MAP: Record<string, string> = {
  'altdorf.ch': '/source-icons/altdorf-geminde.png',
  'eventfrog.ch': '/source-icons/eventfrog.png',
  'gemeinde-andermatt.ch': '/source-icons/gemeinde-andermatt.png',
  'kbu.ch': '/source-icons/kbu.png',
  'musikschule-uri.ch': '/source-icons/musikschule-uri.png',
  'schule-altdorf.ch': '/source-icons/schule-altdorf.png',
  'uri.ch': '/source-icons/uri-ch.png',
  'www.uri.ch': '/source-icons/uri-ch.png',
  'uri-swiss.ch': '/source-icons/uri-swiss.png',
  'uri.swiss': '/source-icons/uri-swiss.png',
  'Uri Tourismus': '/source-icons/uri-swiss.png',
  'urnerwochenblatt.ch': '/source-icons/urnerwochenblatt.png',
  'Volley Uri': '/source-icons/volleyuri.png',
};

/** Map source_name from the API to a friendly display name */
export const SOURCE_DISPLAY_NAME: Record<string, string> = {
  'altdorf.ch': 'Gemeinde Altdorf',
  'eventfrog.ch': 'Eventfrog',
  'gemeinde-andermatt.ch': 'Gemeinde Andermatt',
  'kbu.ch': 'Kantonsbibliothek Uri',
  'musikschule-uri.ch': 'Musikschule Uri',
  'schule-altdorf.ch': 'Schule Altdorf',
  'uri.ch': 'Uri.ch',
  'www.uri.ch': 'Uri.ch',
  'uri-swiss.ch': 'Uri Tourismus',
  'uri.swiss': 'Uri Tourismus',
  'urnerwochenblatt.ch': 'Urner Wochenblatt',
};

/** Get the display name for a source, falling back to the raw source_name */
export function getSourceDisplayName(sourceName: string): string {
  return SOURCE_DISPLAY_NAME[sourceName] || sourceName;
}

/** Get the icon URL for a source */
export function getSourceIcon(sourceName: string, fallbackImageUrl?: string): string | undefined {
  return SOURCE_ICON_MAP[sourceName] || fallbackImageUrl || undefined;
}
