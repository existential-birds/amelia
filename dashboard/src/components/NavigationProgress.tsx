/**
 * @fileoverview Navigation loading progress indicator.
 */

/**
 * Displays an animated progress bar during route transitions.
 *
 * Shows a pulsing progress indicator at the top of the viewport.
 * Used by React Router during navigation loading states.
 *
 * @returns The progress bar UI
 */
export function NavigationProgress() {
  return (
    <div className="absolute top-0 left-0 right-0 h-1 bg-primary/20 z-50">
      <div
        className="h-full bg-primary transition-all duration-300"
        style={{ width: '30%', animation: 'progress-pulse 1s ease-in-out infinite' }}
      />
    </div>
  );
}
