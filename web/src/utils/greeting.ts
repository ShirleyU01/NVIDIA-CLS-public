export function buildTimeOfDayGreeting(now: Date, name: string): string {
  const hour = now.getHours()

  // Keep wording aligned with the Excalidraw pattern.
  if (hour < 12) {
    return `Good Morning, ${name}`
  }
  if (hour < 17) {
    return `Good Afternoon, ${name}`
  }
  return `Good Evening, ${name}`
}
