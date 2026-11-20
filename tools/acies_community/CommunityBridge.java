package org.acies.community;

import android.app.Activity;
import android.content.Context;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.MalformedURLException;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URL;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.cert.CertificateFactory;
import java.util.concurrent.Semaphore;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

/** Connects ACIES's native HTTPS requests and gateway socket to the configured server. */
public final class CommunityBridge {
    private static final int TIMEOUT = 8000;
    private static final URL ORIGIN;
    private static SSLSocketFactory tls;
    private static volatile String token;
    private static volatile ServerSocket listener;

    static {
        try {
            ORIGIN = new URL(BuildConfig.ORIGIN);
        } catch (MalformedURLException error) {
            throw new IllegalStateException(error);
        }
    }

    static synchronized SSLSocketFactory tls(Context context) throws IOException {
        if (tls != null) return tls;
        if (!BuildConfig.LOCAL_CA) {
            tls = HttpsURLConnection.getDefaultSSLSocketFactory();
            return tls;
        }
        try (InputStream input = context.getAssets().open("community-ca.pem")) {
            KeyStore trust = KeyStore.getInstance(KeyStore.getDefaultType());
            trust.load(null);
            trust.setCertificateEntry("aces-local", CertificateFactory.getInstance("X.509").generateCertificate(input));
            TrustManagerFactory managers = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
            managers.init(trust);
            SSLContext ssl = SSLContext.getInstance("TLS");
            ssl.init(null, managers.getTrustManagers(), null);
            tls = ssl.getSocketFactory();
            return tls;
        } catch (GeneralSecurityException error) {
            throw new IOException("Could not load the server certificate", error);
        }
    }

    public static void attach(Activity activity) {
        try {
            CommunitySession.init(activity.getApplicationContext());
            SSLSocketFactory ssl = tls(activity);
            ServerSocket local = new ServerSocket();
            local.bind(new InetSocketAddress("127.0.0.1", 0), 4);
            listener = local;
            new Thread(() -> forwardConnections(local, ssl), "Acies gateway listener").start();
        } catch (IOException error) {
            throw new IllegalStateException("Could not start the game connection", error);
        }
    }

    static void setToken(String session) {
        token = session;
    }

    public static URL rewriteUrl(String value) throws IOException {
        URL source = new URL(value);
        if ((source.getHost().equalsIgnoreCase("live.saintjoy.co.kr")
                || source.getHost().equalsIgnoreCase("col-glob-lb01.srv.creagames.com"))) {
            if (nativeApi(source)) return new URL(ORIGIN, source.getFile());
            throw new MalformedURLException("The original ACIES service is closed");
        }
        return source;
    }

    private static boolean nativeApi(URL url) {
        return url.getPath().startsWith("/api/client/") || url.getPath().startsWith("/api/client-secure/");
    }

    private static int port(URL url) {
        return url.getPort() == -1 ? url.getDefaultPort() : url.getPort();
    }

    public static void configure(HttpURLConnection connection) throws IOException {
        URL url = connection.getURL();
        if (!nativeApi(url) || !url.getProtocol().equals("https")
                || !ORIGIN.getHost().equalsIgnoreCase(url.getHost()) || port(url) != port(ORIGIN)) return;
        ServerSocket local = listener;
        String session = token;
        if (local == null || (session == null && !url.getPath().equals("/api/client/admission"))) {
            throw new IOException("Sign in before starting ACIES");
        }
        connection.setInstanceFollowRedirects(false);
        if (session != null) connection.setRequestProperty("Authorization", "Bearer " + session);
        connection.setRequestProperty("X-Acies-Gateway-Port", Integer.toString(local.getLocalPort()));
        ((HttpsURLConnection) connection).setSSLSocketFactory(tls);
    }

    static HttpsURLConnection accountConnection(Context context, String path) throws IOException {
        HttpsURLConnection connection = (HttpsURLConnection) new URL(ORIGIN, "/community/" + path).openConnection();
        connection.setSSLSocketFactory(tls(context));
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(TIMEOUT);
        connection.setReadTimeout(TIMEOUT);
        return connection;
    }

    private static void forwardConnections(ServerSocket server, SSLSocketFactory ssl) {
        Semaphore slots = new Semaphore(4);
        while (!server.isClosed()) {
            try {
                Socket nativeSocket = server.accept();
                if (!slots.tryAcquire()) {
                    nativeSocket.close();
                    continue;
                }
                new Thread(() -> {
                    try {
                        forward(nativeSocket, ssl);
                    } finally {
                        slots.release();
                    }
                }, "Acies gateway connection").start();
            } catch (IOException error) {
                close(server);
            }
        }
    }

    private static void forward(Socket nativeSocket, SSLSocketFactory factory) {
        try (Socket local = nativeSocket; Socket remote = new Socket()) {
            local.setTcpNoDelay(true);
            // A game login begins with a TC header. Wait for it before opening the upstream socket.
            local.setSoTimeout(TIMEOUT);
            InputStream input = local.getInputStream();
            int first = input.read();
            if (first != 'T') return;
            remote.connect(new InetSocketAddress(ORIGIN.getHost(), BuildConfig.GATEWAY_PORT), TIMEOUT);
            remote.setTcpNoDelay(true);
            remote.setSoTimeout(TIMEOUT);
            try (SSLSocket secure = (SSLSocket) factory.createSocket(remote, ORIGIN.getHost(), BuildConfig.GATEWAY_PORT, true)) {
                SSLParameters parameters = secure.getSSLParameters();
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                secure.setSSLParameters(parameters);
                secure.startHandshake();
                secure.setSoTimeout(0);
                local.setSoTimeout(0);
                OutputStream outbound = secure.getOutputStream();
                outbound.write(first);
                Thread upload = new Thread(() -> pump(input, outbound, secure, local), "Acies gateway upload");
                upload.start();
                pump(secure.getInputStream(), local.getOutputStream(), secure, local);
            }
        } catch (IOException error) {
            android.util.Log.d("AciesCommunity", "Gateway connection closed: " + error.getClass().getSimpleName());
        }
    }

    private static void pump(InputStream source, OutputStream target, Socket upstream, Socket downstream) {
        try {
            byte[] bytes = new byte[8192];
            for (int count; (count = source.read(bytes)) != -1;) target.write(bytes, 0, count);
        } catch (IOException ignored) {
            // Losing either side ends this connection and lets ACIES reconnect.
        } finally {
            close(upstream);
            close(downstream);
        }
    }

    private static void close(java.io.Closeable resource) {
        try {
            resource.close();
        } catch (IOException ignored) {
        }
    }
}
