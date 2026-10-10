"""Exploratory analysis of the character cards of a run (no LLM): name groups, alias clusters, link evidence.
Run with:  PYTHONPATH=. python graph/link_analysis.py   (environment loaded)"""
import re, json, collections as C
from common.db import connect
c=connect("app").cursor()
c.execute("select season,episode,payload from episode_extractions x join extraction_runs r using(run_id) where r.label='v3-extract-001' and stage='reviewed'")
rows=c.fetchall()
TITLES=r"^(mr|mrs|ms|miss|dr|sir|mister|senator|officer|detective|captain)\.?\s+"
def norm(n): 
    n=n.lower().strip(); n=re.sub(r"[^a-z0-9' .\-]","",n); n=re.sub(TITLES,"",n); return " ".join(n.split())
cards=[]
for s,e,p in rows:
    for ch in p["characters"]:
        names=[norm(n) for n in ch["names"] if norm(n)]
        cards.append(dict(ep=(s,e),lid=ch["local_id"],names=names,desc=ch["description"],present=ch["present"],lines=ch["lines"]))
print("cards",len(cards))
# name strings
cnt=C.Counter(n for cd in cards for n in set(cd["names"]))
print("distinct normalised name strings:",len(cnt))
print("strings in >=20 cards:",sum(1 for v in cnt.values() if v>=20),"| >=5:",sum(1 for v in cnt.values() if v>=5),"| exactly 1 card:",sum(1 for v in cnt.values() if v==1))
# alias clusters: names co-listed in the same card are the same person
parent={}
def f(x):
    parent.setdefault(x,x)
    while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
    return x
def u(a,b): parent[f(a)]=f(b)
for cd in cards:
    for n in cd["names"]: f(n)
    for a,b in zip(cd["names"],cd["names"][1:]): u(a,b)
clusters=C.defaultdict(set)
for n in list(parent): clusters[f(n)].add(n)
print("alias clusters (names joined when listed on one card):",len(clusters))
csize=C.Counter()
for cd in cards:
    if cd["names"]: csize[f(cd["names"][0])]+=1
big=[(k,v) for k,v in csize.most_common() if v>=20]
print("clusters with >=20 cards:",len(big)," covering",sum(v for _,v in big),"of",len(cards),"cards")
print("clusters with 5-19 cards:",sum(1 for k,v in csize.items() if 5<=v<20),"| 2-4:",sum(1 for k,v in csize.items() if 2<=v<5),"| 1:",sum(1 for k,v in csize.items() if v==1))
print("\ntop 25 clusters:")
for k,v in csize.most_common(25): print(f"  {v:4} cards  {sorted(clusters[k])[:6]}")
# hard rule: same cluster twice in one episode
dup=0; dupex=[]
byep=C.defaultdict(list)
for cd in cards: byep[cd["ep"]].append(cd)
for ep,cs in byep.items():
    seen=C.Counter(f(cd["names"][0]) for cd in cs if cd["names"])
    for k,v in seen.items():
        if v>1: dup+=1; dupex.append((ep,sorted(clusters[k])[:3],v))
print("\nepisodes where one alias cluster has 2+ cards (cannot-link candidates or duplicates):",dup); print(dupex[:8])
# shared first token across different clusters
tok=C.defaultdict(set)
for k,names in clusters.items():
    for n in names: tok[n.split()[0]].add(k)
amb=[(t,len(ks),sum(csize[k] for k in ks)) for t,ks in tok.items() if len(ks)>1 and sum(csize[k] for k in ks)>=8]
print("\nfirst tokens shared by >1 cluster (>=8 cards):",len(amb)); print(sorted(amb,key=lambda x:-x[2])[:25])
json.dump({"cards":len(cards)},open("/dev/null","w"))

print("\n=== the 660-card cluster: its names"); k=csize.most_common(1)[0][0]; print(sorted(clusters[k]))
print("\n=== primary-name groups (names[0] only, no merging): top 40")
prim=C.Counter(cd["names"][0] for cd in cards if cd["names"])
print(prim.most_common(40))
print("\nprimary names that appear in 2+ cards of the same episode (generic or duplicate cards):")
dupn=C.Counter()
for ep,cs in byep.items():
    c2=C.Counter(cd["names"][0] for cd in cs if cd["names"])
    for n,v in c2.items():
        if v>1: dupn[n]+=1
print(dupn.most_common(15))
print("\ncards with a present=False (mentioned only):",sum(1 for cd in cards if not cd['present']))
print("names with 'and'/'&'/ ',' (joint) :",[n for n in cnt if re.search(r" and | & ",n)][:8])

print("\n=== candidate pairs: primary names sharing a word, with link evidence")
prim_cards=C.defaultdict(list)
for cd in cards:
    if cd["names"]: prim_cards[cd["names"][0]].append(cd)
def cochars(group): 
    s=C.Counter()
    for cd in group:
        for o in byep[cd["ep"]]:
            if o is not cd and o["names"]: s[o["names"][0]]+=1
    return s
pairs=[]
names_=[n for n,g in prim_cards.items() if len(g)>=4]
for i,a in enumerate(names_):
    for b in names_[i+1:]:
        ta,tb=set(a.split()),set(b.split())
        if ta&tb and (ta<=tb or tb<=ta or a.split()[0]==b.split()[0]):
            ga,gb=prim_cards[a],prim_cards[b]
            both_card=sum(1 for cd in cards if a in cd["names"] and b in cd["names"])
            ea={cd["ep"] for cd in ga}; eb={cd["ep"] for cd in gb}
            same_ep=len(ea&eb)
            ca,cb=cochars(ga),cochars(gb)
            top=lambda x:{n for n,_ in x.most_common(12)}
            jac=len(top(ca)&top(cb))/max(len(top(ca)|top(cb)),1)
            sa=sorted({e[0] for e in ea}); sb=sorted({e[0] for e in eb})
            pairs.append((a,b,len(ga),len(gb),both_card,same_ep,round(jac,2),f"S{sa[0]}-{sa[-1]}",f"S{sb[0]}-{sb[-1]}"))
print(f"{'A':16}{'B':20}{'#A':>4}{'#B':>4} {'listed on one card':>19} {'same episode':>13} {'co-chars':>9}  seasons")
for p in sorted(pairs,key=lambda p:-(p[2]+p[3]))[:22]: print(f"{p[0]:16}{p[1]:20}{p[2]:>4}{p[3]:>4} {p[4]:>19} {p[5]:>13} {p[6]:>9}  {p[7]} / {p[8]}")

print("\n=== size of primary-name groups")
sizes=C.Counter(len(g) for g in prim_cards.values())
big=[g for g in prim_cards.values() if len(g)>=10]; mid=[g for g in prim_cards.values() if 3<=len(g)<10]; small=[g for g in prim_cards.values() if len(g)<3]
print("distinct primary names:",len(prim_cards)," | >=10 cards:",len(big),"groups =",sum(map(len,big)),"cards | 3-9:",len(mid),"=",sum(map(len,mid)),"| 1-2:",len(small),"=",sum(map(len,small)))
import random; random.seed(3)
print("\nrandom 3-9 card groups:")
for n,g in random.sample([(n,g) for n,g in prim_cards.items() if 3<=len(g)<10],14): print(f"  {n!r:22} {len(g)} cards  e.g. {g[0]['desc'][:70]}")
print("\nrandom single-card names (with the other names on the card):")
sing=[(n,g[0]) for n,g in prim_cards.items() if len(g)==1]
for n,cd in random.sample(sing,22): print(f"  {n!r:24} {cd['names'][1:4]} | S{cd['ep'][0]}E{cd['ep'][1]} | {cd['desc'][:60]}")
print("\nsingleton names whose other names on the card contain a big-group name (nickname of a main character?):")
bign={n for n,g in prim_cards.items() if len(g)>=10}
n_hit=0
for n,cd in sing:
    if any(o in bign for o in cd["names"][1:]) : n_hit+=1
print(n_hit,"of",len(sing))

print("\n=== evidence-only merge candidates between ANY two primary-name groups (no LLM)")
# A and B are candidates when cards of A also list B's primary name (or vice versa), or both names sit on one card.
pn=set(prim_cards)
ev=C.Counter()
for cd in cards:
    if not cd["names"]: continue
    a=cd["names"][0]
    for other in cd["names"][1:]:
        if other in pn and other!=a: ev[tuple(sorted((a,other)))]+=1
res=[]
for (a,b),n in ev.items():
    ea={cd["ep"] for cd in prim_cards[a]}; eb={cd["ep"] for cd in prim_cards[b]}
    same=len(ea&eb)
    # separate-card co-presence is the cannot-link evidence
    res.append((a,b,n,len(prim_cards[a]),len(prim_cards[b]),same))
ok=[r for r in res if r[5]==0 and r[2]>=1]
bad=[r for r in res if r[5]>0]
print("pairs with name evidence:",len(res),"| never together in an episode (merge candidates):",len(ok),"| appear together in some episode (cannot be the same):",len(bad))
print("\nmerge candidates (A, B, #cards that list the other name, size A, size B):")
for r in sorted(ok,key=lambda r:-r[2])[:40]: print(f"  {r[0]!r:22} {r[1]!r:24} listed {r[2]:>2}x   sizes {r[3]}/{r[4]}")
print("\ncannot-link examples (listed as aliases but seen together as separate people):")
for r in sorted(bad,key=lambda r:-r[2])[:12]: print(f"  {r[0]!r:18} {r[1]!r:18} listed {r[2]:>2}x  together in {r[5]} episodes")
