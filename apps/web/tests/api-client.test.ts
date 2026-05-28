import { describe, expect, it } from "vitest";
import { formatApiErrorMessage } from "../src/api/client";

describe("formatApiErrorMessage", () => {
  it("formats FastAPI validation detail arrays", () => {
    const message = formatApiErrorMessage(
      {
        detail: [
          {
            loc: ["body", "email"],
            msg: "value is not a valid email address",
          },
        ],
      },
      "Unprocessable Entity",
    );

    expect(message).toBe("body.email: value is not a valid email address");
  });

  it("uses string details directly", () => {
    expect(formatApiErrorMessage({ detail: "LLM API key is not configured" }, "Bad Request")).toBe(
      "LLM API key is not configured",
    );
  });
});
