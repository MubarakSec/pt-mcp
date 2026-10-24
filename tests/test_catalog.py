import json
import pathlib
import re
import unittest
from live_bridge import LiveBridge

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_registered_names_and_schemas_match_catalog(self):
        descriptors = {}
        for filename in ('PtMcpServer.java', 'PresentationTools.java'):
            source = (ROOT / 'backend/java/src/main/java/com/ptmcp' / filename).read_text()
            # Registrations have literal descriptions/schemas followed by a handler lambda.
            for match in re.finditer(r'tool\(jm,\s*"(pt_[^"]+)"\s*,(.*?)\(ex,\s*req\)\s*->', source, re.S):
                name, body = match.groups()
                blocks = re.findall(r'"""\s*(.*?)\s*"""', body, re.S)
                if blocks:
                    schema = json.loads(blocks[0])
                else:
                    literals = re.findall(r'"(?:\\.|[^"\\])*"', body)
                    combined = ''.join(json.loads(value) for value in literals)
                    schema = json.loads(combined[combined.index('{'):])
                self.assertNotIn(name, descriptors)
                descriptors[name] = schema
        catalog = {t['name']: t for t in LiveBridge._catalog_tools()}
        self.assertEqual(set(descriptors), set(catalog))
        for name, schema in descriptors.items():
            with self.subTest(name=name):
                self.assertEqual(schema, catalog[name]['inputSchema'])
        prefixed = LiveBridge.cached_tools()
        self.assertEqual({t['name'] for t in prefixed}, {'pt_live_' + n[3:] for n in descriptors})
        readonly = set(re.findall(r'"(pt_[^"]+)"', re.search(
            r'java.util.Set.of\((.*?)\).contains\(name\)',
            (ROOT / 'backend/java/src/main/java/com/ptmcp/PtMcpServer.java').read_text(), re.S).group(1)))
        self.assertEqual(readonly, {n for n,t in catalog.items() if t['annotations']['readOnlyHint']})

    def test_add_device_compatibility(self):
        tool = next(t for t in LiveBridge._catalog_tools() if t['name'] == 'pt_add_device')
        self.assertEqual(tool['inputSchema']['required'], ['type', 'model', 'x', 'y'])
        self.assertIn('name', tool['inputSchema']['properties'])
