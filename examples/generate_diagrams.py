"""Regenerate portable review examples: python3 examples/generate_diagrams.py."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagrams import plan_layout,export_svg


def campus():
    devices=[{'name':'Campus Core','type':'router','model':'2911'}]
    groups=[];links=[]
    for building,count in [('Engineering',20),('Operations',20),('المبنى الثالث',10)]:
        switch=building+' Switch'
        names=[switch]+[f'{building} PC {i+1:02}' for i in range(count)]
        groups.append({'name':building,'devices':names})
        devices.extend({'name':n,'type':'switch' if n==switch else 'pc'} for n in names)
        links.extend([{'dev_a':'Campus Core','dev_b':switch}]+[{'dev_a':switch,'dev_b':n} for n in names[1:]])
    return {'devices':devices,'links':links},groups


def main():
    directory=Path(__file__).resolve().parent
    snapshot,groups=campus()
    small={'devices':[{'name':'Edge Router','type':'router'},{'name':'Access Switch','type':'switch'},
                      {'name':'مكتب الإدارة 192.0.2.10','type':'pc'},{'name':'Unknown <&> model'}],
           'links':[{'dev_a':'Edge Router','dev_b':'Access Switch'},
                    {'dev_a':'Access Switch','dev_b':'مكتب الإدارة 192.0.2.10'}]}
    for name,data,regions in [('campus-50',snapshot,groups),('small-network',small,None)]:
        plan=plan_layout(data,regions)
        (directory/(name+'.json')).write_text(json.dumps({'snapshot':data,'groups':regions,'plan':plan},ensure_ascii=False,indent=2)+'\n')
        export_svg(data,str(directory/(name+'.svg')),plan,title='Campus · 50 PCs' if regions else 'Office network',overwrite=True)


if __name__=='__main__':main()
