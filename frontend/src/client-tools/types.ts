export interface ClientToolDeclaration {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ClientToolStatus {
  id: string;
  label: string;
  ariaLabel: string;
}

export interface ClientToolProviderAvailability {
  providerId: string;
  available: boolean;
}
