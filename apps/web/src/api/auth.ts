import { api } from "./client";
import type { AuthResponse, User } from "./types";

export const authApi = {
  signIn: (email: string, password: string) =>
    api<AuthResponse>("/auth/signin", { method: "POST", body: { email, password } }),

  signUp: (email: string, password: string, displayName: string) =>
    api<AuthResponse>("/auth/signup", {
      method: "POST",
      body: { email, password, display_name: displayName },
    }),

  me: () => api<User>("/auth/me"),
};
