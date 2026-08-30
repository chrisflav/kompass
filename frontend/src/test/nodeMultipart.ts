/**
 * Node's own FormData / File / Blob classes.
 *
 * jsdom installs its own, but it implements no fetch, so `Response` here is
 * Node's — and the FormData a Node `Response` parses out is therefore Node's
 * too. Round-tripping an empty multipart body is the least fragile way to reach
 * that constructor without depending on undici's package layout.
 */
const probe = await new Response("--b--\r\n", {
  headers: { "content-type": "multipart/form-data; boundary=b" },
}).formData();

const NodeFormData = probe.constructor as typeof globalThis.FormData;

const { Blob: NodeBlob, File: NodeFile } = (await import("node:buffer")) as unknown as {
  Blob: typeof globalThis.Blob;
  File: typeof globalThis.File;
};

export default { FormData: NodeFormData, File: NodeFile, Blob: NodeBlob };
