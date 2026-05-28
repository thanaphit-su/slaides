import { api } from "./client";
import type { Workspace, WorkspacePatch } from "./types";

export const workspaceApi = {
  get: () => api<Workspace>("/workspace"),
  patch: (body: WorkspacePatch) => api<Workspace>("/workspace", { method: "PATCH", body }),
};
