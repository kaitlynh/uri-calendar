import { describe, it, expect } from 'vitest';
import { getSourceIcon } from '../sources';

describe('getSourceIcon', () => {
  it('returns icon path for a valid filename', () => {
    expect(getSourceIcon('altdorf-geminde.png')).toBe('/source-icons/altdorf-geminde.png');
  });

  it('returns undefined when filename is null', () => {
    expect(getSourceIcon(null)).toBeUndefined();
  });

  it('returns undefined when filename is undefined', () => {
    expect(getSourceIcon(undefined)).toBeUndefined();
  });

  it('returns undefined for empty string', () => {
    // Empty string is falsy — treated as "no icon"
    expect(getSourceIcon('')).toBeUndefined();
  });

  it('preserves the original filename (no encoding)', () => {
    expect(getSourceIcon('uri-swiss.png')).toBe('/source-icons/uri-swiss.png');
  });
});
