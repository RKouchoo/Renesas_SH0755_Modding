import java.io.File;
import java.lang.reflect.*;
import java.util.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;
import com.romraider.Settings;
import com.romraider.util.SettingsManager;
import com.romraider.logger.ecu.comms.manager.QueryManagerImpl;
import com.romraider.logger.ecu.comms.query.*;
import com.romraider.logger.ecu.definition.EcuAddressImpl;
import com.romraider.logger.ecu.definition.EcuData;
import com.romraider.logger.ecu.definition.EcuDataType;
import com.romraider.logger.ecu.definition.Module;
import com.romraider.logger.ecu.ui.MessageListener;
import com.romraider.io.protocol.ssm.iso9141.SSMLoggerProtocol;

// Offline integration check: actual XML selections, pending reload, real A8 builder.
public class ProfileReloadCheck {
    public static void main(String[] args) throws Exception {
        Field settings = SettingsManager.class.getDeclaredField("settings");
        settings.setAccessible(true);
        settings.set(null, new Settings());
        Document defs = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(new File(args[0]));
        Map<String, Element> definitions = new HashMap<String, Element>();
        for (String tag : new String[] {"parameter", "ecuparam"}) {
            NodeList entries = defs.getElementsByTagName(tag);
            for (int i = 0; i < entries.getLength(); i++) {
                Element e = (Element) entries.item(i);
                definitions.put(e.getAttribute("id"), e);
            }
        }
        for (int file = 1; file < args.length; file++) {
            QueryManagerImpl manager = new QueryManagerImpl(noCalls(EcuInitCallback.class), noCalls(MessageListener.class));
            Document profile = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(new File(args[file]));
            NodeList selections = profile.getElementsByTagName("parameter");
            List<EcuData> selected = new ArrayList<EcuData>();
            for (int i = 0; i < selections.getLength(); i++) {
                Element selection = (Element) selections.item(i);
                if (!"selected".equals(selection.getAttribute("livedata"))) continue;
                if (!"selected".equals(selection.getAttribute("dash"))) throw new AssertionError("view mismatch");
                final Element def = definitions.get(selection.getAttribute("id"));
                NodeList addresses = def.getElementsByTagName("address");
                if (addresses.getLength() != 1) throw new AssertionError("ambiguous address");
                Element addr = (Element) addresses.item(0);
                final EcuAddressImpl address = new EcuAddressImpl(addr.getTextContent().trim(),
                        addr.hasAttribute("length") ? Integer.parseInt(addr.getAttribute("length")) : 1, -1);
                EcuData data = (EcuData) Proxy.newProxyInstance(EcuData.class.getClassLoader(), new Class<?>[] {EcuData.class},
                        new InvocationHandler() {
                    public Object invoke(Object proxy, Method method, Object[] a) {
                        if (method.getName().equals("getName")) return def.getAttribute("name");
                        if (method.getName().equals("getAddress")) return address;
                        if (method.getName().equals("getDataType")) return EcuDataType.PARAMETER;
                        throw new AssertionError(method.toString());
                    }
                });
                selected.add(data);
            }
            for (String view : new String[] {"Data", "Dashboard"}) {
                for (EcuData data : selected) manager.addQuery(view, data);
                for (EcuData data : selected) manager.removeQuery(view, data);
                for (EcuData data : selected) manager.addQuery(view, data);
            }
            Method update = QueryManagerImpl.class.getDeclaredMethod("updateQueryList");
            update.setAccessible(true);
            update.invoke(manager);
            Field mapField = QueryManagerImpl.class.getDeclaredField("queryMap");
            mapField.setAccessible(true);
            Map<?, ?> map = (Map<?, ?>) mapField.get(manager);
            if (map.size() != selected.size() * 2) throw new AssertionError("lost subscriptions: " + map.size());
            List<EcuQuery> queries = new ArrayList<EcuQuery>();
            for (Object query : map.values()) queries.add((EcuQuery) query);
            byte[] request = new SSMLoggerProtocol().constructReadAddressRequest(
                    new Module("ECU", new byte[]{0x10}, "ECU", new byte[]{(byte)0xF0}, true), queries);
            if (request.length != 136 || (request[3] & 255) != 131) throw new AssertionError("unexpected request size");
            int sum = 0;
            for (int i = 0; i < request.length - 1; i++) sum += request[i] & 255;
            if ((sum & 255) != (request[request.length - 1] & 255)) throw new AssertionError("checksum");
            System.out.println(new File(args[file]).getName() + ": " + selected.size() +
                    " channels, " + map.size() + " view subscriptions; 43 addresses, 136-byte request, valid checksum");
        }
    }
    @SuppressWarnings("unchecked")
    static <T> T noCalls(Class<T> type) {
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, new InvocationHandler() {
            public Object invoke(Object proxy, Method method, Object[] args) { throw new AssertionError(method.toString()); }
        });
    }
}
