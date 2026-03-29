/** Build the icon URL from an icon_filename (from the DB), or return undefined */
export function getSourceIcon(iconFilename?: string | null): string | undefined {
  return iconFilename ? `/source-icons/${iconFilename}` : undefined;
}
