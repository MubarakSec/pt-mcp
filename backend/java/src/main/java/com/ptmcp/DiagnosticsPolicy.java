package com.ptmcp;

import java.time.Instant;
import java.util.*;
import java.util.regex.*;

/** Pure evidence evaluation. Incomplete observations never imply success. */
public final class DiagnosticsPolicy {
    private DiagnosticsPolicy() { }
    public static final int MAX_CHECKS=20;
    public static final int MAX_OUTPUT=32768;

    public static Map<String,Object> result(String status,String reason,Map<String,?> evidence) {
        var r=new LinkedHashMap<String,Object>();
        r.put("status",status);r.put("reason",reason);r.put("observed_at",Instant.now().toString());
        r.put("evidence",new LinkedHashMap<>(evidence));return r;
    }
    public static String aggregate(List<Map<String,Object>> results) {
        if(results.isEmpty()) return "unknown";
        if(results.stream().anyMatch(r -> "fail".equals(r.get("status")))) return "fail";
        return results.stream().allMatch(r -> "pass".equals(r.get("status")))?"pass":"unknown";
    }
    public static List<Map<String,Object>> validateChecks(Object value) {
        if(!(value instanceof List<?> list) || list.isEmpty() || list.size()>MAX_CHECKS)
            throw new IllegalArgumentException("checks must contain 1..20 objects");
        var checks=new ArrayList<Map<String,Object>>();
        for(Object item:list) {
            if(!(item instanceof Map<?,?> m)) throw new IllegalArgumentException("checks must be objects");
            Object kind=m.get("kind");
            if(!(kind instanceof String k) || !Set.of("boot","terminal_idle","dhcp_address","trunk_vlan").contains(k))
                throw new IllegalArgumentException("unsupported check kind");
            var allowed=new HashSet<>(Set.of("kind","device"));
            if(k.equals("dhcp_address") || k.equals("trunk_vlan")) allowed.add("iface");
            if(k.equals("trunk_vlan")) allowed.add("vlans");
            if(!allowed.containsAll(m.keySet())) throw new IllegalArgumentException("unexpected check field");
            var check=new LinkedHashMap<String,Object>();check.put("kind",k);
            check.put("device",PresentationPolicy.name(m.get("device")));
            if(allowed.contains("iface")) check.put("iface",PresentationPolicy.name(m.get("iface")));
            if(k.equals("trunk_vlan")) {
                if(!(m.get("vlans") instanceof List<?> vlans) || vlans.isEmpty() || vlans.size()>128)
                    throw new IllegalArgumentException("vlans must contain 1..128 unique VLAN IDs");
                var normalized=new ArrayList<Integer>();
                for(Object vlan:vlans) {
                    int n=PresentationPolicy.coordinate(vlan);
                    if(n<1 || n>4094 || normalized.contains(n)) throw new IllegalArgumentException("VLAN IDs must be unique integers 1..4094");
                    normalized.add(n);
                }
                check.put("vlans",normalized);
            }
            checks.add(check);
        }
        return checks;
    }
    public static Map<String,Object> boot(Boolean power,Boolean booting) {
        var evidence=new LinkedHashMap<String,Object>();
        evidence.put("source","Device.getPower / CiscoDevice.isBooting");
        evidence.put("powered",power);evidence.put("booting",booting);
        return result(Boolean.FALSE.equals(power)?"fail":power==null || booting==null?"unknown":booting?"fail":"pass",
                Boolean.FALSE.equals(power)?"powered_off":booting==null?"boot_state_unavailable":booting?"boot_in_progress":"boot_finished",evidence);
    }
    private static boolean usableObservation(String output,boolean completed,String sdkStatus,boolean truncated) {
        return completed && !truncated && output!=null && output.length()<=MAX_OUTPUT
                && "success".equals(CliPolicy.classify(sdkStatus,output)) && !output.contains("--More--");
    }
    private static String excerpt(String output) {
        return output==null?"":output.substring(0,Math.min(output.length(),4096));
    }
    private static boolean usableIpv4(String address) {
        String[] parts=address.split("\\.",-1);
        if(parts.length!=4) return false;
        int[] n=new int[4];
        for(int i=0;i<4;i++) {
            if(!parts[i].matches("[0-9]{1,3}")) return false;
            n[i]=Integer.parseInt(parts[i]);if(n[i]>255) return false;
        }
        return n[0]!=0 && n[0]!=127 && n[0]<224 && !(n[0]==169 && n[1]==254);
    }
    public static Map<String,Object> address(Boolean dhcp,String iface,String output,boolean completed,String sdkStatus,boolean truncated) {
        var e=new LinkedHashMap<String,Object>();e.put("source","live ipconfig; per-interface DHCP mode");
        e.put("configured_dhcp",dhcp);e.put("iface",iface);e.put("sdk_status",sdkStatus);
        e.put("completed",completed);e.put("output_truncated",truncated);e.put("output_excerpt",excerpt(output));
        e.put("lease_server_confirmed",false);
        if(Boolean.FALSE.equals(dhcp)) return result("fail","dhcp_disabled",e);
        if(!usableObservation(output,completed,sdkStatus,truncated)) return result("unknown","active_address_not_observed",e);
        String selected=null;int sectionCount=0;String address=null;int addressCount=0;
        for(String line:output.split("\\R")) {
            Matcher heading=Pattern.compile("^\\s*(.+?)\\s+Connection\\s*:(?:.*)$",Pattern.CASE_INSENSITIVE).matcher(line);
            if(heading.matches()) {
                selected=heading.group(1).trim();if(selected.equalsIgnoreCase(iface)) sectionCount++;
            } else if(selected!=null && selected.equalsIgnoreCase(iface)) {
                Matcher ip=Pattern.compile("^\\s*(?:IPv4 Address|IP Address)[. \\t]*:\\s*([0-9.]+)\\s*$",Pattern.CASE_INSENSITIVE).matcher(line);
                if(ip.matches()) {address=ip.group(1);addressCount++;}
            }
        }
        if(sectionCount!=1 || addressCount!=1) return result("unknown","interface_address_ambiguous_or_missing",e);
        e.put("observed_address",address);
        if(dhcp==null) return result("unknown","per_interface_dhcp_mode_unknown",e);
        String[] octets=address.split("\\.",-1);
        if(octets.length!=4 || Arrays.stream(octets).anyMatch(n -> !n.matches("[0-9]{1,3}") || Integer.parseInt(n)>255))
            return result("unknown","malformed_address_observation",e);
        return result(usableIpv4(address)?"pass":"fail",usableIpv4(address)?"usable_address_in_dhcp_mode":"no_usable_dhcp_address",e);
    }
    static String canonicalInterface(String name) {
        String s=name.toLowerCase(Locale.ROOT).replaceAll("\\s+","");
        return s.replaceFirst("^(?:gigabitethernet|gig|gi)(?=[0-9])","gi")
                .replaceFirst("^(?:fastethernet|fa)(?=[0-9])","fa")
                .replaceFirst("^(?:tengigabitethernet|ten|te)(?=[0-9])","te")
                .replaceFirst("^(?:ethernet|eth|et)(?=[0-9])","et");
    }
    private static Set<Integer> vlanSet(String value) {
        value=value.trim().toLowerCase(Locale.ROOT);
        if(value.equals("none")) return Set.of();
        if(value.equals("all")) { var all=new HashSet<Integer>();for(int i=1;i<=4094;i++)all.add(i);return all; }
        if(!value.matches("[0-9,-]+")) throw new IllegalArgumentException("unrecognized VLAN list");
        var values=new HashSet<Integer>();
        for(String part:value.split(",",-1)) {
            String[] bounds=part.split("-",-1);
            if(bounds.length<1 || bounds.length>2) throw new IllegalArgumentException("invalid VLAN range");
            int first=Integer.parseInt(bounds[0]);int last=bounds.length==1?first:Integer.parseInt(bounds[1]);
            if(first<1 || last>4094 || first>last) throw new IllegalArgumentException("invalid VLAN range");
            for(int i=first;i<=last;i++) values.add(i);
        }
        return values;
    }
    public static Map<String,Object> trunk(String iface,List<Integer> expected,String output,boolean completed,String sdkStatus,boolean truncated) {
        var e=new LinkedHashMap<String,Object>();e.put("source","show interfaces trunk");e.put("iface",iface);
        e.put("expected_vlans",expected);e.put("sdk_status",sdkStatus);e.put("completed",completed);
        e.put("output_truncated",truncated);e.put("output_excerpt",excerpt(output));
        if(!usableObservation(output,completed,sdkStatus,truncated)) return result("unknown","trunk_observation_unavailable",e);
        String target=canonicalInterface(iface);String operational=null;int operationalCount=0;
        var observed=new LinkedHashMap<String,Set<Integer>>();var counts=new HashMap<String,Integer>();
        String section="";boolean malformed=false;
        for(String line:output.split("\\R")) {
            String text=line.trim();String lower=text.toLowerCase(Locale.ROOT).replaceAll("\\s+"," ");
            if(lower.startsWith("port ")) {
                if(lower.contains("vlans in spanning tree forwarding")) section="forwarding";
                else if(lower.contains("vlans allowed and active")) section="active";
                else if(lower.contains("vlans allowed on trunk")) section="allowed";
                else if(lower.contains("encapsulation") && lower.contains("status")) section="operational";
                else section="";
                continue;
            }
            if(Set.of("allowed","active","forwarding").contains(section) && text.matches("[0-9, -]+")) malformed=true;
            String[] fields=text.split("\\s+",2);
            if(fields.length<2 || !canonicalInterface(fields[0]).equals(target)) continue;
            if(section.equals("operational")) {
                String[] cells=fields[1].split("\\s+");
                if(cells.length!=4) {malformed=true;continue;}
                operational=cells[2].toLowerCase(Locale.ROOT);operationalCount++;
            } else if(Set.of("allowed","active","forwarding").contains(section)) {
                counts.merge(section,1,Integer::sum);
                try { observed.put(section,vlanSet(fields[1])); }
                catch(IllegalArgumentException bad) {malformed=true;}
            }
        }
        e.put("operational_status",operational);
        if(malformed || operationalCount!=1) return result("unknown","unrecognized_or_ambiguous_trunk_table",e);
        if(!"trunking".equals(operational)) return result("fail","interface_not_trunking",e);
        if(!observed.keySet().containsAll(Set.of("allowed","active","forwarding"))
                || counts.values().stream().anyMatch(n -> n!=1)) return result("unknown","incomplete_trunk_sections",e);
        var missing=new LinkedHashMap<String,List<Integer>>();
        for(String key:List.of("allowed","active","forwarding")) {
            var absent=expected.stream().filter(n -> !observed.get(key).contains(n)).toList();
            missing.put(key,absent);
            e.put(key+"_expected_present",expected.stream().filter(observed.get(key)::contains).toList());
        }
        e.put("missing_vlans",missing);
        boolean pass=missing.values().stream().allMatch(List::isEmpty);
        return result(pass?"pass":"fail",pass?"vlans_allowed_active_and_forwarding":"vlan_state_mismatch",e);
    }
}
