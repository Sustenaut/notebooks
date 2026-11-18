declare module "*.css?inline" {
  const css: string;
  export default css;
}

// pubtest is JavaScript without types: what the scenarios' steps use of it.
declare module "@sustenaut/pubtest" {
  export function register(api: unknown, options?: { runner?: "cucumber" | "quickpickle"; client?: unknown }): void;
}
