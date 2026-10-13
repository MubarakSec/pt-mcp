package com.ptmcp;

import com.cisco.pt.ipc.events.HTTPClientEvent;
import com.cisco.pt.ipc.events.HTTPClientEventListener;
import com.cisco.pt.ipc.sim.HTTPClient;
import com.cisco.pt.ipc.sim.HTTPServer;
import com.cisco.pt.ipc.sim.HostPort;
import com.cisco.pt.ipc.sim.Pc;
import com.cisco.pt.ipc.sim.Device;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import java.io.IOException;
import java.io.StringReader;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

/** Read-only endpoint and simulated HTTP helpers backed by Cisco's IPC SDK. */
public final class EndpointServiceFeatures {
    private static final long DEFAULT_HTTP_TIMEOUT_SECONDS = 15;

    private EndpointServiceFeatures() { }

    /** Reads SDK fields; gateway/DNS require the live device XML fallback. */
    public static Map<String, Object> readEndpoint(Pc pc, HostPort port) {
        if (pc == null || port == null) throw new IllegalArgumentException("pc and port are required");

        String ip = port.getIpAddress() == null ? null : port.getIpAddress().toString();
        String mask = port.getSubnetMask() == null ? null : port.getSubnetMask().toString();
        boolean dhcp = pc.getDhcpFlag() || port.isDhcpClientOn();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("device", pc.getName());
        result.put("iface", port.getName());
        result.put("ip", ip);
        result.put("mask", mask);
        result.put("dhcp", dhcp);
        result.put("gateway", null);
        result.put("dns", null);
        result.put("gateway_dns_source", "unavailable: Cisco IPC SDK exposes setters only");
        result.put("note", dhcp
                ? "ip/mask are the SDK's stored interface fields and may be the last static values, not the active DHCP lease; dhcp is authoritative for the configured mode."
                : "gateway and dns are unavailable through the installed Cisco IPC SDK; no stored setter inputs or file snapshot were used.");
        return result;
    }

    /** Live IPC XML fallback; no network file is saved or reopened. */
    public static Map<String, Object> readEndpoint(Pc pc, HostPort port, Device device) {
        Map<String, Object> result = readEndpoint(pc, port);
        Map<String, Object> xmlFields = readEndpointXmlFields(device, port);
        result.putAll(xmlFields);
        if (xmlFields.get("gateway") != null || xmlFields.get("dns") != null) {
            result.put("note", "gateway/dns came from the live device serializeToXml() response; IP/mask/DHCP came from HostPort/Pc getters. With dhcp=true, IP/mask may be stale static fields.");
        }
        return result;
    }

    public static Map<String, Object> readEndpointXmlFields(Device device, String ifaceName) {
        return readEndpointXmlFields(device, ifaceName, null);
    }

    private static Map<String, Object> readEndpointXmlFields(Device device, HostPort port) {
        return readEndpointXmlFields(device, port.getName(), port.getMacAddress() == null
                ? null : port.getMacAddress().toString());
    }

    private static Map<String, Object> readEndpointXmlFields(Device device, String ifaceName, String macAddress) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("gateway", null);
        result.put("dns", null);
        result.put("gateway_dns_source", "unavailable: live device XML did not expose recognized fields for this interface");
        if (device == null || ifaceName == null || ifaceName.isBlank()) return result;
        String xml;
        try {
            xml = device.serializeToXml();
            if (xml == null || xml.isBlank()) return result;
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            Document doc = factory.newDocumentBuilder().parse(new InputSource(new StringReader(xml)));
            Element root = doc.getDocumentElement();
            Element portElement = findPortElement(root, ifaceName, macAddress);
            String gateway = findField(portElement, "PORT_GATEWAY", "GATEWAY");
            String dns = findField(portElement, "PORT_DNS", "DNS", "DNS_SERVER", "DNS_SERVER_IP");
            if (gateway == null) gateway = findDirectField(root, "GATEWAY");
            if (gateway == null) gateway = findFieldUnder(root, "ENGINE", "GATEWAY");
            if (dns == null) dns = findDirectField(root, "DNS", "DNS_SERVER", "DNS_SERVER_IP");
            if (dns == null) dns = findFieldUnder(root, "ENGINE", "DNS", "DNS_SERVER", "DNS_SERVER_IP");
            if (dns == null) dns = findFieldUnder(root, "DNS_CLIENT", "SERVER_IP");
            result.put("gateway", gateway);
            result.put("dns", dns);
            if (gateway != null || dns != null) {
                result.put("gateway_dns_source", "live_device_xml");
            }
        } catch (Exception ignored) {
            result.put("gateway_dns_source", "unavailable: could not parse live device XML");
        }
        return result;
    }

    private static Element findPortElement(Element root, String ifaceName, String macAddress) {
        NodeList all = root.getElementsByTagName("*");
        for (int i = 0; i < all.getLength(); i++) {
            Node node = all.item(i);
            if (!(node instanceof Element element)) continue;
            String tag = element.getTagName().toUpperCase();
            if (!tag.equals("PORT") && !tag.equals("HOST_PORT") && !tag.equals("INTERFACE")) continue;
            if (macAddress != null && normalizeMac(macAddress).equals(normalizeMac(findField(element, "MACADDRESS")))) {
                return element;
            }
            for (String attr : new String[]{"name", "port_name", "interface", "id"}) {
                if (ifaceName.equalsIgnoreCase(element.getAttribute(attr))) return element;
            }
            String childName = findField(element, "PORT_NAME", "INTERFACE_NAME");
            if (ifaceName.equalsIgnoreCase(childName)) return element;
        }
        return null;
    }

    private static String normalizeMac(String value) {
        return value == null ? "" : value.replaceAll("[^A-Fa-f0-9]", "").toLowerCase();
    }
    private static String findField(Element root, String... tags) {
        if (root == null) return null;
        NodeList found = root.getElementsByTagName("*");
        for (int i = 0; i < found.getLength(); i++) {
            Node item = found.item(i);
            if (!(item instanceof Element element) || !hasTag(element, tags)) continue;
            String value = element.hasAttribute("value") ? element.getAttribute("value") : element.getTextContent();
            if (value != null && !value.isBlank()) return value.trim();
        }
        return null;
    }
    private static String findDirectField(Element root, String... tags) {
        if (root == null) return null;
        NodeList children = root.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            Node node = children.item(i);
            if (node instanceof Element element && hasTag(element, tags)) {
                String value = element.hasAttribute("value") ? element.getAttribute("value") : element.getTextContent();
                if (value != null && !value.isBlank()) return value.trim();
            }
        }
        return null;
    }
    private static boolean hasTag(Element element, String... tags) {
        for (String tag : tags) {
            if (tag.equalsIgnoreCase(element.getTagName())) return true;
        }
        return false;
    }

    private static String findFieldUnder(Element root, String parentTag, String... childTags) {
        NodeList all = root.getElementsByTagName("*");
        for (int i = 0; i < all.getLength(); i++) {
            if (all.item(i) instanceof Element parent && hasTag(parent, parentTag)) {
                String value = findDirectField(parent, childTags);
                if (value != null) return value;
            }
        }
        return null;
    }

    /** Uses the simulated PC browser; response_type is Cisco's enum, not a numeric HTTP status. */
    public static Map<String, Object> requestPage(HTTPClient client, String url) throws IOException {
        return requestPage(client, url, DEFAULT_HTTP_TIMEOUT_SECONDS);
    }

    public static Map<String, Object> requestPage(HTTPClient client, String url, long timeoutSeconds)
            throws IOException {
        if (client == null) throw new IllegalArgumentException("HTTP client is required");
        if (url == null || url.isBlank()) throw new IllegalArgumentException("url is required");
        if (timeoutSeconds < 1) throw new IllegalArgumentException("timeoutSeconds must be positive");

        CountDownLatch completed = new CountDownLatch(1);
        String clientUuid = client.getObjectUUID().toString();
        AtomicReference<HTTPClientEvent.OnDone> response = new AtomicReference<>();
        HTTPClientEventListener listener = event -> {
            if (event instanceof HTTPClientEvent.OnDone done && url.equals(done.url)
                    && event.objectUUID != null && clientUuid.equals(event.objectUUID.toString())) {
                response.set(done);
                completed.countDown();
            }
        };

        var events = client.getPacketTracerSession().getEventManager().getHTTPClientEvents();
        events.addListener(listener);
        try {
            boolean accepted = client.go(url);
            if (!accepted) {
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("url", url);
                result.put("accepted", false);
                result.put("response_type", null);
                result.put("content", null);
                result.put("note", "Packet Tracer did not accept the simulated browser request.");
                return result;
            }

            boolean done;
            try {
                done = completed.await(timeoutSeconds, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IOException("Interrupted while waiting for Packet Tracer's HTTP response", interrupted);
            }
            if (!done) {
                client.cancel();
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("url", url);
                result.put("accepted", true);
                result.put("response_type", null);
                result.put("content", null);
                result.put("timed_out", true);
                return result;
            }

            HTTPClientEvent.OnDone doneEvent = response.get();
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("url", doneEvent.url);
            result.put("accepted", true);
            result.put("response_type", doneEvent.responseType == null ? null : doneEvent.responseType.name());
            result.put("server_ip", doneEvent.serverIp == null ? null : doneEvent.serverIp.toString());
            result.put("content", doneEvent.content);
            result.put("timed_out", false);
            return result;
        } finally {
            events.removeListener(listener);
        }
    }
    public static Map<String, Object> readHttpService(HTTPServer server) {
        if (server == null) throw new IllegalArgumentException("HTTP server is required");
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("enabled", server.isEnabled());
        result.put("port", server.getPortNumber());
        result.put("index_page", server.getPage("index.html"));
        return result;
    }
}
