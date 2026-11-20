package org.acies.community;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.net.ssl.HttpsURLConnection;

/** Network and Android Keystore bridge for the game's native account picker. */
public final class CommunitySession {
    private static final String KEY_ALIAS = "acies_community_session";
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private static Context context;
    private static SharedPreferences saved;
    private static volatile String result;

    static void init(Context application) {
        context = application;
        saved = application.getSharedPreferences("community-account", Context.MODE_PRIVATE);
    }

    public static String savedName() {
        return saved.getString("username", "");
    }

    public static void begin(int mode, String username, String password, String invite) {
        result = null;
        WORKER.execute(() -> {
            try {
                String token;
                if (mode == 3) {
                    token = loadSession();
                    if (token == null) throw new ServerError(401, "Sign in again to continue.");
                    request("session", "GET", token, null);
                } else {
                    JSONObject body = new JSONObject().put("username", username.trim()).put("password", password);
                    if (mode == 2) body.put("invite", invite.trim());
                    JSONObject reply = request(mode == 2 ? "register" : "login", "POST", null, body);
                    token = reply.getString("token");
                    storeSession(token, reply.getString("username"));
                }
                CommunityBridge.setToken(token);
                result = "";
            } catch (ServerError error) {
                if (mode == 3 && error.status == 401) {
                    saved.edit().clear().apply();
                    result = "Your session has expired. Sign in again.";
                } else {
                    result = error.getMessage();
                }
            } catch (Exception error) {
                result = "Could not complete the request. Check your connection and try again.";
            }
        });
    }

    public static String poll() {
        String finished = result;
        if (finished != null) result = null;
        return finished;
    }

    private static JSONObject request(String path, String method, String token, JSONObject body) throws Exception {
        HttpsURLConnection connection = CommunityBridge.accountConnection(context, path);
        try {
            connection.setRequestMethod(method);
            if (token != null) connection.setRequestProperty("Authorization", "Bearer " + token);
            if (body != null) {
                byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
                connection.setRequestProperty("Content-Type", "application/json");
                connection.setDoOutput(true);
                connection.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream output = connection.getOutputStream()) {
                    output.write(bytes);
                }
            }
            int response = connection.getResponseCode();
            if (response >= 200 && response < 300) return readJson(connection.getInputStream());
            String message = "The server could not complete the request.";
            try {
                message = readJson(connection.getErrorStream()).optString("error", message);
            } catch (Exception ignored) {
            }
            throw new ServerError(response, message);
        } finally {
            connection.disconnect();
        }
    }

    private static JSONObject readJson(InputStream source) throws Exception {
        if (source == null) return new JSONObject();
        try (InputStream input = source; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] bytes = new byte[1024];
            for (int count; (count = input.read(bytes)) != -1;) {
                if (output.size() + count > 8192) throw new IOException("Account response too large");
                output.write(bytes, 0, count);
            }
            return new JSONObject(output.toString("UTF-8"));
        }
    }

    private static SecretKey sessionKey() throws GeneralSecurityException, IOException {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) return (SecretKey) store.getKey(KEY_ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }

    private static void storeSession(String token, String display) throws GeneralSecurityException, IOException {
        if (!token.matches("acs_[A-Za-z0-9_-]{43}")) throw new IOException("Invalid session format");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, sessionKey());
        String content = Base64.encodeToString(cipher.doFinal(token.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        String iv = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP);
        if (!saved.edit().putString("token", content).putString("iv", iv).putString("username", display).commit()) {
            throw new IOException("Could not save the session");
        }
    }

    private static String loadSession() throws GeneralSecurityException, IOException {
        String content = saved.getString("token", "");
        if (content.isEmpty()) return null;
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        byte[] iv = Base64.decode(saved.getString("iv", ""), Base64.NO_WRAP);
        cipher.init(Cipher.DECRYPT_MODE, sessionKey(), new GCMParameterSpec(128, iv));
        return new String(cipher.doFinal(Base64.decode(content, Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }

    private static final class ServerError extends IOException {
        final int status;

        ServerError(int status, String message) {
            super(message);
            this.status = status;
        }
    }
}
