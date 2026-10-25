/**
 * The browser half of registering a security key. The server sends the
 * creation options as JSON with base64url strings where the WebAuthn API takes
 * binary buffers, and verifies the answer as JSON again; this converts both
 * ways and checks nothing itself.
 */

type Json = Record<string, unknown>;

export function webauthnSupported(): boolean {
  return typeof window !== "undefined" && "PublicKeyCredential" in window && !!navigator.credentials;
}

function toBytes(base64url: string): ArrayBuffer {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64 + "===".slice((base64.length + 3) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function toBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Run `navigator.credentials.create` with the server's options; the answer as JSON. */
export async function createCredential(options: Json): Promise<Json> {
  const user = options.user as Json;
  const exclude = (options.excludeCredentials as Json[] | undefined) ?? [];
  const publicKey = {
    ...options,
    challenge: toBytes(options.challenge as string),
    user: { ...user, id: toBytes(user.id as string) },
    excludeCredentials: exclude.map((c) => ({ ...c, id: toBytes(c.id as string) })),
  } as unknown as PublicKeyCredentialCreationOptions;
  const credential = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null;
  if (!credential) throw new Error("Der Sicherheitsschlüssel hat nicht geantwortet.");
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      attestationObject: toBase64url(response.attestationObject),
      transports: response.getTransports?.() ?? [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}
