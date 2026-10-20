declare module "virtual:component-api" {
  const docs: Record<string, {
    name: string;
    props: Array<{ name: string; type: string; required: boolean; defaultValue: string; description: string; native: boolean }>;
  }>;
  export default docs;
}
