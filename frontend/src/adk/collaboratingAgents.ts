export class CollaboratorApiError extends Error {
  constructor(
    public status: number,
    public reason?: string,
  ) {
    super(`Collaborator request failed (${status})`);
  }
}
