/**
 * @fileoverview CSV export utilities.
 */

/**
 * Escape a CSV field value to handle special characters.
 * Prefixes formula-injection characters and quotes fields containing
 * commas, double quotes, or newlines.
 */
export function escapeCsvField(value: string | number): string {
  let text = String(value);
  if (/^\s*[=+\-@\t\0]/.test(text)) {
    text = `'${text}`;
  }
  const needsQuote = /[",\n\r]/.test(text);
  text = text.replace(/"/g, '""');
  return needsQuote ? `"${text}"` : text;
}

/**
 * Export tabular data as a downloadable CSV file.
 *
 * @param rows - Array of rows, each row an array of cell values.
 * @param filename - Download filename (without extension).
 */
export function downloadCSV(rows: (string | number)[][], filename: string): void {
  const csv = rows.map((r) => r.map(escapeCsvField).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
