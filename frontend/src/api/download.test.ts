import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, downloadArtifact } from "./http";
import { api, http, HttpResponse, server } from "../test/server";

/**
 * `downloadArtifact` ends in a synthetic <a download> click. jsdom implements
 * neither `URL.createObjectURL` nor a real download, so stub the object-URL pair
 * and watch the anchor instead — that is the whole observable contract.
 */
function captureDownload() {
  const created: Blob[] = [];
  const revoked: string[] = [];
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: (blob: Blob) => {
      created.push(blob);
      return "blob:kompass/1";
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: (url: string) => void revoked.push(url),
  });

  const anchors: HTMLAnchorElement[] = [];
  const realClick = HTMLAnchorElement.prototype.click;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    anchors.push(this);
  });
  return { created, revoked, anchors, restore: () => void (HTMLAnchorElement.prototype.click = realClick) };
}

describe("downloadArtifact", () => {
  beforeEach(() => {
    localStorage.setItem("kompass_token", "tok");
  });

  it("saves the file under the caller's filename", async () => {
    const cap = captureDownload();
    server.use(
      http.get(api("/api/finance/documents/statements/1/summary"), () =>
        HttpResponse.json({}, { headers: { "Content-Type": "application/pdf" } }),
      ),
    );

    await downloadArtifact("/api/finance/documents/statements/1/summary", {
      filename: "Abrechnung.pdf",
    });

    expect(cap.anchors).toHaveLength(1);
    expect(cap.anchors[0].download).toBe("Abrechnung.pdf");
    expect(cap.anchors[0].href).toBe("blob:kompass/1");
    // The anchor is removed again and the object URL released.
    expect(document.querySelector("a[download]")).toBeNull();
    expect(cap.revoked).toEqual(["blob:kompass/1"]);
    cap.restore();
  });

  it("falls back to the filename the server sent", async () => {
    const cap = captureDownload();
    server.use(
      http.get(api("/api/members/documents/groups/5/checklist"), () =>
        HttpResponse.json({}, {
          headers: { "Content-Disposition": 'attachment; filename="Checkliste Gruppe.pdf"' },
        }),
      ),
    );

    await downloadArtifact("/api/members/documents/groups/5/checklist");
    expect(cap.anchors[0].download).toBe("Checkliste Gruppe.pdf");
    cap.restore();
  });

  it("decodes an RFC 5987 filename", async () => {
    const cap = captureDownload();
    server.use(
      http.get(api("/api/members/documents/groups/5/checklist"), () =>
        HttpResponse.json({}, {
          headers: {
            "Content-Disposition": "attachment; filename*=UTF-8''Ausfahrt%20S%C3%BCdtirol.pdf",
          },
        }),
      ),
    );

    await downloadArtifact("/api/members/documents/groups/5/checklist");
    expect(cap.anchors[0].download).toBe("Ausfahrt Südtirol.pdf");
    cap.restore();
  });

  it("names the file 'download' when nothing else says otherwise", async () => {
    const cap = captureDownload();
    server.use(http.get(api("/api/x"), () => HttpResponse.json({})));
    await downloadArtifact("/api/x");
    expect(cap.anchors[0].download).toBe("download");
    cap.restore();
  });

  it("sends a JSON body and the bearer token on a POST", async () => {
    const cap = captureDownload();
    let seen: { auth: string | null; type: string | null; body: unknown } | null = null;
    server.use(
      http.post(api("/api/members/documents/members/export"), async ({ request }) => {
        seen = {
          auth: request.headers.get("Authorization"),
          type: request.headers.get("Content-Type"),
          body: await request.json(),
        };
        return HttpResponse.json({});
      }),
    );

    await downloadArtifact("/api/members/documents/members/export", {
      method: "POST",
      body: { ids: [1, 2] },
    });

    expect(seen).toEqual({
      auth: "Bearer tok",
      type: "application/json",
      body: { ids: [1, 2] },
    });
    cap.restore();
  });

  it("omits the Authorization header when signed out", async () => {
    const cap = captureDownload();
    localStorage.removeItem("kompass_token");
    let auth: string | null = "unset";
    server.use(
      http.get(api("/api/startpage/public/x"), ({ request }) => {
        auth = request.headers.get("Authorization");
        return HttpResponse.json({});
      }),
    );

    await downloadArtifact("/api/startpage/public/x");
    expect(auth).toBeNull();
    cap.restore();
  });

  it("raises the API error a failing document endpoint returns", async () => {
    const cap = captureDownload();
    server.use(
      http.get(api("/api/members/documents/groups/5/checklist"), () =>
        HttpResponse.json({ detail: "members.view_group" }, { status: 403 }),
      ),
    );

    await expect(
      downloadArtifact("/api/members/documents/groups/5/checklist"),
    ).rejects.toMatchObject({ status: 403, message: "Dazu fehlt dir die Berechtigung." });
    // Nothing is written to disk on a failure.
    expect(cap.anchors).toHaveLength(0);
    cap.restore();
  });

  it("still raises when the error body is not JSON", async () => {
    const cap = captureDownload();
    server.use(
      http.get(api("/api/x"), () => new HttpResponse("<html>500</html>", { status: 500 })),
    );

    await expect(downloadArtifact("/api/x")).rejects.toBeInstanceOf(ApiError);
    cap.restore();
  });

  it("blobs a real binary payload rather than re-encoding it", async () => {
    const cap = captureDownload();
    server.use(
      http.get(api("/api/x"), () =>
        HttpResponse.arrayBuffer(new Uint8Array([1, 2, 3]).buffer, {
          headers: { "Content-Type": "application/pdf" },
        }),
      ),
    );

    await downloadArtifact("/api/x", { filename: "x.pdf" });
    expect(cap.created).toHaveLength(1);
    expect(cap.created[0].size).toBe(3);
    cap.restore();
  });
});
