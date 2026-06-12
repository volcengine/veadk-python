// Generic representation of a generated VeADK agent project: a named
// collection of files, used by the project preview / editor component.

export interface ProjectFile {
  path: string;
  content: string;
}

export interface AgentProject {
  name: string;
  files: ProjectFile[];
}
