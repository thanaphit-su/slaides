import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import AccountMenu from "@/components/AccountMenu.vue";

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark", "light");
});

describe("AccountMenu", () => {
  it("opens from avatar, switches theme, and emits sign out", async () => {
    const wrapper = mount(AccountMenu, {
      props: {
        userName: "Thanaphit S.",
        userEmail: "thanaphit.su@gmail.com",
      },
      global: {
        stubs: {
          Icon: true,
        },
      },
    });

    await wrapper.get('[data-testid="account-avatar-button"]').trigger("click");

    expect(wrapper.get('[data-testid="account-menu"]').text()).toContain("Thanaphit S.");

    await wrapper.get('[data-testid="account-theme-dark"]').trigger("click");

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("slaides:theme-mode")).toBe("dark");

    await wrapper.get('[data-testid="account-menu-signout"]').trigger("click");

    expect(wrapper.emitted("sign-out")).toEqual([[]]);
  });
});
