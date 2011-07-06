#!/usr/bin/env python

"""
pgdia -- Simple database diagrammer for Postgres.
=================================================

Accepts a schema dump [generated via pg_dump -s], emits a diagram.

Render the diagram using the graphvis suite -- `dot` or `fdp` give good
results.

Example:
    pgdia.py --schema wrmsdb-dump.sql request_ | fdp -Tsvg -o a.svg

Caveats:
    * This is not how you parse SQL. It works on the output of pg_dump 8.4,
      for the things I'm interested in, but is in no way robust or complete.
    * This was a very quick hack. Much of the code is total garbage.

Blame:
    Chris Forbes <chrisf@catalyst.net.nz>
"""

from optparse import OptionParser
import re
import sys

def gen_diagram():
    parser = OptionParser(usage="usage: %proc [options] re...")
    parser.add_option( '-s', "--schema", dest="schema",
        help="load database schema from FILE", metavar="FILE" )

    options, args = parser.parse_args()
    def should_keep(r):
        """ Should we keep this relation? """
        if not len(args):
            return True
        for x in args:
            if re.match( x, r ):
                return True
        return False

    relations = {}

    src = open( options.schema, 'r' )
    current_relation = None

    for l in src.xreadlines():
        try:
            l = l.replace('\n','').replace('ONLY ','')
            m = re.match( '^(?:ALTER|CREATE) TABLE ([^ ]+)', l )
            if m:
                if m.group(1).startswith( 'public.' ):
                    continue
                current_relation = m.group(1)
                if current_relation not in relations:
                    relations[ current_relation ] = {}
            elif re.match( '^\);$', l ):
                current_relation = None
            elif current_relation:
                mm = re.sub( '^\s+([^ ]+)[ ]', r'\1\t', l )
                mm = re.sub( ',$', '', mm )
                mm = re.sub( 'DEFAULT .{5,}', r'DEFAULT ...', mm ).split('\t')
                if len(mm) < 2:
                    continue
                if mm[0] in [ 'AFTER', 'FOR', 'EXECUTE', 'CONSTRAINT' ]:
                    continue
                if 'ADD' in mm[0]:
                    if 'PRIMARY KEY' in mm[1]:
                        m3 = re.search( r'PRIMARY KEY \((.+)\);$', mm[1] )
                        pk_attribs = m3.group(1).split(', ')
                        for a in pk_attribs:
                            relations[ current_relation ][a]['pk'] = True
                        continue
                    if 'FOREIGN KEY' in mm[1]:
                        m4 = re.search(
      r'CONSTRAINT ([^ ]+) FOREIGN KEY \(([^)]+)\) REFERENCES ([^(]+)', mm[1] )
                        fk_name = m4.group(1)
                        fk_attribs = m4.group(2).split(', ')
                        fk_target = m4.group(3)

                        invalid = False
                        for a in fk_attribs:
                            if a not in relations[ current_relation ]:
                                invalid = True
                                print >> sys.stderr,\
                                  'Dropping bogus FK due to attrib %s.%s' %\
                                      (current_relation,a)
                        if invalid:
                            continue

                        if '_fk' not in relations[current_relation]:
                            relations[current_relation][ '_fk' ] = { 'n': 1 }

                        fk_info = relations[ current_relation ][ '_fk' ]
                        fk_index = fk_info['n']       # allocate fk id
                        fk_info['n'] = fk_index + 1
                        fk_info[fk_name] = { 'n': fk_index, 'to': fk_target }

                        for a in fk_attribs:
                            relations[ current_relation ][a]\
                               ['fk_%s' % fk_index] = True
                        continue
                    else:
                        continue   # ignore these.
                relations[ current_relation ][ mm[0] ] = { 'type': mm[1] }
        except Exception, e:
            print >> sys.stderr, 'While parsing %s: %s' % (l,repr(e))
            # try to recover.
            current_relation = None

    # filter based on the REs provided by the user
    for r in [_r for _r in relations][:]:
        if not should_keep(r):
            del relations[r]

    for r in relations:
        if '_fk' in relations[r]:
            fk = relations[r]['_fk']
            for f in [_f for _f in fk if _f != 'n'][:]:
                if fk[f][ 'to' ] not in relations:
                    print >> sys.stderr, 'dropping fk %s->%s due to filter' %\
                        (r,fk[f][ 'to' ])
                    del fk[f]

    # output as dot
    print 'digraph pgdia'
    print '{'

    def format_attrib_a(a,av):
        z = '%s\\l' % a
        return z
    def format_attrib_b(a,av):
        z = '%s\\l' % av['type']
        return z
    def format_attrib_c(a,av):
        z = '%s' % ('PK' if 'pk' in av else ' ')
        for q in av:
            if 'fk_' in q:
                z = z + ' ' + q.replace('fk_','FK')
        z = z + '\\l'
        return z

    print '\tgraph [overlap=false]'
    print '\tnode [shape=record fontname="Bitstream Vera Mono" fontsize=8]'
    print '\tedge [fontname="Bitstream Vera Mono" fontsize=8]'

    for r,rv in relations.items():
#        print '\t%s [shape=square, color=blue]' % r

        attribs = ''.join(
            [format_attrib_a(a,av) for a,av in rv.items() if a != '_fk'])
        attribs2 = ''.join(
            [format_attrib_b(a,av) for a,av in rv.items() if a != '_fk'])
        attribs3 = ''.join(
            [format_attrib_c(a,av) for a,av in rv.items() if a != '_fk'])
        label = '{%s|{%s|%s|%s}}'% (r,attribs,attribs2,attribs3)
        print '\t%s [label="%s"]' % (r,label)

#        for a,av in rv.items():
 #           print '\t %s [shape=plaintext]' % a

        if '_fk' in rv:
            for fk, fkv in rv['_fk'].items():
                if 'n' != fk:
                    attribs = [ a for a,av in rv.items() \
                        if ('fk_%s' % fkv['n']) in av ]
                    label = '%s\\l(%s)' % (fk, ','.join(attribs))
                    print '\t%s -> %s [label="%s"]' % (r,fkv['to'],label)

    print '}'

if __name__ == '__main__':
    gen_diagram()
