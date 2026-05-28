import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/workspace" },
    { path: "/signin", name: "signin", component: () => import("@/pages/Signin.vue") },
    {
      path: "/join",
      name: "join-session",
      component: () => import("@/pages/Signin.vue"),
      props: { startGuest: true },
    },
    {
      path: "/workspace",
      name: "workspace",
      component: () => import("@/pages/Workspace.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/editor/:deckId",
      name: "editor",
      component: () => import("@/pages/Editor.vue"),
      meta: { requiresAuth: true, requiresApproval: true },
      props: true,
    },
    {
      path: "/present/:sessionId",
      name: "presenter",
      component: () => import("@/pages/Presenter.vue"),
      meta: { requiresAuth: true, requiresApproval: true },
      props: true,
    },
    {
      path: "/j/:code",
      name: "guest-join",
      component: () => import("@/pages/Signin.vue"),
      props: (route) => ({ joinCode: route.params.code }),
    },
    {
      path: "/audience/:sessionId",
      name: "audience",
      component: () => import("@/pages/Audience.vue"),
      props: true,
    },
    {
      path: "/decks/:deckId/preview",
      name: "deck-preview",
      component: () => import("@/pages/Preview.vue"),
      meta: { requiresAuth: true, requiresApproval: true },
      props: true,
    },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.requiresAuth && !auth.isSignedIn) {
    return { name: "signin", query: { next: to.fullPath } };
  }
  if (to.meta.requiresApproval && auth.isSignedIn && !auth.isApproved) {
    return { name: "workspace", query: { pending: "1" } };
  }
  if (to.name === "signin" && auth.isSignedIn && auth.isApproved) {
    return { name: "workspace" };
  }
});
