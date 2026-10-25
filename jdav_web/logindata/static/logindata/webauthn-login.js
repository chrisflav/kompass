// The WebAuthn half of the sign-in pages: a form marked `data-webauthn-form`
// asks its `data-options-url` for a challenge, has the browser sign it with a
// security key, and submits the signed answer in its `credential` field. The
// server checks everything; this only converts between the browser's binary
// buffers and the base64url strings the server speaks.
(function () {
  "use strict";

  if (!window.PublicKeyCredential || !navigator.credentials) {
    return;
  }

  function toBytes(base64url) {
    var base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
    var binary = atob(base64 + "===".slice((base64.length + 3) % 4));
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  function toBase64url(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = "";
    for (var i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function requestOptions(publicKey) {
    publicKey.challenge = toBytes(publicKey.challenge);
    (publicKey.allowCredentials || []).forEach(function (c) {
      c.id = toBytes(c.id);
    });
    return publicKey;
  }

  function assertionJSON(credential) {
    var r = credential.response;
    return {
      id: credential.id,
      rawId: toBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: toBase64url(r.clientDataJSON),
        authenticatorData: toBase64url(r.authenticatorData),
        signature: toBase64url(r.signature),
        userHandle: r.userHandle ? toBase64url(r.userHandle) : null,
      },
      clientExtensionResults: credential.getClientExtensionResults(),
    };
  }

  function showError() {
    document.querySelectorAll("[data-webauthn-error]").forEach(function (el) {
      el.hidden = false;
    });
  }

  document.querySelectorAll("[data-webauthn]").forEach(function (el) {
    el.hidden = false;
  });

  document.querySelectorAll("form[data-webauthn-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.elements.credential.value) {
        return;
      }
      event.preventDefault();
      fetch(form.dataset.optionsUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": form.elements.csrfmiddlewaretoken.value },
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("options " + response.status);
          }
          return response.json();
        })
        .then(function (options) {
          return navigator.credentials.get({ publicKey: requestOptions(options.publicKey) });
        })
        .then(function (credential) {
          form.elements.credential.value = JSON.stringify(assertionJSON(credential));
          form.submit();
        })
        .catch(showError);
    });
  });
})();
