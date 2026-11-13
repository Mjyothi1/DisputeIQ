import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { getReviewerKey } from "@/api/auth";
import { api } from "@/api/client";
import { LoginGate } from "@/components/LoginGate";

function renderGate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <LoginGate />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LoginGate", () => {
  beforeEach(() => sessionStorage.clear());

  it("stores the key only after the server accepts it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ name: "asha" }), { status: 200 })),
    );
    renderGate();
    await userEvent.type(screen.getByLabelText(/reviewer access key/i), "demo-key-12345");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await vi.waitFor(() => expect(getReviewerKey()).toBe("demo-key-12345"));
  });

  it("rejects a wrong key and keeps the user signed out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "Invalid" }), { status: 401 })),
    );
    renderGate();
    await userEvent.type(screen.getByLabelText(/reviewer access key/i), "wrong-key-1234");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not recognised/i);
    expect(getReviewerKey()).toBe("");
  });

  it("sends the key as a bearer token and never a client-typed analyst name", async () => {
    sessionStorage.setItem("diq-reviewer-key", "demo-key-12345");
    const f = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", f);
    await api.review(1, { action: "APPROVE" });
    const [, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer demo-key-12345");
    expect(String(init.body)).not.toContain("analyst");
  });
});
