import argparse
import time
from itertools import groupby

import requests


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Subscribe to all new communities on a lemmy instance!')
    parser.add_argument('-i', '--include', nargs='+', help='only include these instances (space separated)')
    parser.add_argument('-e', '--exclude', nargs='+', help='exclude these instances (space separated)')
    parser.add_argument('-l', '--local', help='local instance to subscribe to i.e. lemmy.co.uk', required=True)
    parser.add_argument('-u', '--username', help='username to subscribe with i.e. fed_sub_bot', required=True)
    parser.add_argument('-p', '--password', help='password for user', required=True)
    parser.add_argument('-2', '--two-factor', help='two factor auth code for user', required=False)
    parser.add_argument('-n', '--no-pending', help='skip subscribing to Pending communities', action='store_true')
    parser.add_argument('-s', '--subscribe-only', help='only subscribe to unsubscribed (-n) or unsubscribed/pending communities, do not scrape for and add new communities', action='store_true')
    parser.add_argument('-d', '--discover-only', help='only add new communities to instance list, do not subscribe', action='store_true')
    parser.add_argument('-r', '--rate-limit', help='if specified, will rate limit requests to LOCAL to this many per second (default: 15)', type=int, default=15)
    parser.add_argument('-t', '--top-only', help='top X communities based on active users per day (Lemmy only) (default: 10)', type=int, default=10)
    parser.add_argument('-k', '--skip-kbin', help='if specified, will not discover kbin communities (will still subscribe if they are communities on instance)', action='store_true')
    parser.add_argument('-x', '--unsubscribe-all', help='forgo all other functions and unsubscribe the USER from all communities on instance', action='store_true')
    args = parser.parse_args()

    # define local instance, username, password and include/exclude lists
    local_instance = args.local
    username = args.username
    password = args.password
    no_pending = args.no_pending
    subscribe_only = args.subscribe_only
    discover_only = args.discover_only
    unsubscribe_all = args.unsubscribe_all
    skip_kbin = args.skip_kbin
    mfa_code = args.two_factor

    # enable testing
    debug = False

    if args.top_communities_only is not None:
        top_communities_only = args.top_communities_only
    else:
        top_communities_only = 0

    if args.top_instances_only is not None:
        top_instances_only = args.top_instances_only
    else:
        top_instances_only = 0

    # create new session object for local instance
    with requests.Session() as curSession:
        if mfa_code is None:
            payload = '{"username_or_email": "' + username + '","password": "' + password + '"}'
        else:
            payload = (
                '{"username_or_email": "'
                + username
                + '","password": "'
                + password
                + '","totp_2fa_token": "'
                + mfa_code
                + '"}'
            )
        print("logging in to " + local_instance + " as " + username + "...")
        login_resp = curSession.post(
            "https://" + local_instance + "/api/v3/user/login",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        auth_token = login_resp.json()["jwt"]
        if args.rate_limit is not None:
            rl_sleep = 1 / args.rate_limit
        else:
            rl_sleep = 0

        def discover():
            
            print("fetching lemmy communities (and kbin magazines) from lemmyverse.net...")
            meta = requests.get("https://lemmyverse.net/data/meta.json")
            communities_total = meta.json()["communities"]
            magazines_total = meta.json()["magazines"]
            communities_pages = communities_total // 500
            magazines_pages = magazines_total // 500
            instance_actors = []
            community_actors = []
            
            
            print("fetching instances from lemmyverse.net...")
            instances = requests.get("https://data.lemmyverse.net/data/instance.full.json")
            print("Found " + str(len(instances.json())) + " instances")
            
            getlocalfederation()
            
            if top_instances_only > 0:
                print("Only working with communities from the top " + str(top_instances_only) + " instances.")
                instances_to_use = sorted(instances.json(), key=lambda x: x["counts"]["users"], reverse=True)[:top_instances_only]
                
                for instance in instances_to_use:
                    if instance["baseurl"].lower() == exclude_instances:
                        print("Excluding " + instance["baseurl"].lower() + ' as it is not allowed on your host!')
                    else:
                        instance_actors.append(instance["baseurl"].lower())
                        
                                     
            else:
                for instance in instances.json():
                    if instance["baseurl"].lower() == exclude_instances:
                        print("Excluding " + instance["baseurl"].lower() + ' as it is not allowed on your host.')
                    elif instance['counts']['communities'] == 0:
                        print("Excluding " + instance["baseurl"].lower() + ' as it has 0 communities.')
                    elif instance['private'] is True:
                        print("Excluding " + instance["baseurl"].lower() + ' as it is a private instance')
                    elif instance['counts']['users_active_month'] < 1:
                        print("Excluding " + instance["baseurl"].lower() + ' as it has 0 active users within the last month.')
                    else:
                        instance_actors.append(instance["baseurl"].lower())
                                     
            print('After sorting, the remaining number of instances is ' + str(len(instance_actors)))
            
            if top_communities_only > 0:
                with_baseurl = []
                while communities_pages >= 0:
                    communities = requests.get("https://lemmyverse.net/data/community/" + str(communities_pages) + ".json"                    )
                    for community in communities.json():
                        if (community["counts"]["posts"] > 0 and community["isSuspicious"] is not True and (community["baseurl"] in instance_actors)):
                            #check moved to in instance_actors
                            #and (include_instances == [] or community["baseurl"] in include_instances)
                            
                            tmp_dict = {"baseurl": community["baseurl"],"users_active_day": community["counts"]["users_active_day"],"url": community["url"].lower()}
                            with_baseurl.append(tmp_dict)
                    communities_pages -= 1
                with_baseurl.sort(key=lambda k: k["baseurl"])
                instances = groupby(with_baseurl, key=lambda k: k["baseurl"])
                for instance in instances:
                    top_communities = sorted(
                        instance[1], key=lambda k: k["users_active_day"], reverse=True
                    )[:top_communities_only]
                    for community in top_communities:
                        community_actors.append(community["url"].lower())
            else:
                while communities_pages >= 0:
                    communities = requests.get(
                        "https://lemmyverse.net/data/community/" + str(communities_pages) + ".json"
                    )
                    for community in communities.json():
                        if (community["counts"]["posts"] > 0 and community["isSuspicious"] is not True and (community["baseurl"] in exclude_instances)):
                            #check moved to in instance_actors
                            #and (include_instances == [] or community["baseurl"] in include_instances)                        
                            community_actors.append(community["url"].lower())
                    communities_pages -= 1
            community_count = str(len(community_actors))
            print("got " + community_count + " non-empty Lemmy communities.")
            
            if skip_kbin is False:
                magazine_actors = []
                while magazines_pages >= 0:
                    magazines = requests.get(
                        "https://lemmyverse.net/data/magazines/" + str(magazines_pages) + ".json"
                    )
                    for magazine in magazines.json():
                        if magazine["baseurl"] not in exclude_instances and (
                            include_instances == [] or magazine["baseurl"] in include_instances
                        ):
                            magazine_actors.append(magazine["actor_id"].lower())
                    magazines_pages -= 1
                magazine_count = str(len(magazine_actors))
                print("got " + magazine_count + " kbin magazines.")
            if skip_kbin is False:
                all_actors = community_actors + magazine_actors
            else:
                all_actors = community_actors
            all_actor_count = str(len(all_actors))
            print("enumerating all locally (known) communities (this might take a while)...")
            local_community_id_list = []
            local_community_actor_id_list = []
            new_results = True
            page = 1
            while new_results:
                time.sleep(rl_sleep)
                actor_resp = curSession.get(
                    "https://"
                    + local_instance
                    + "/api/v3/community/list?type_=All&limit=50&page="
                    + str(page)
                    + "&auth="
                    + auth_token,
                    headers={"Content-Type": "application/json"},
                )
                if actor_resp.json()["communities"] != []:
                    for community in actor_resp.json()["communities"]:
                        local_community_id_list.append(community["community"]["id"])
                        local_community_actor_id_list.append(
                            community["community"]["actor_id"].lower()
                        )
                    print(page * 50, end="\r")
                    page += 1
                else:
                    new_results = False
            print("done.")
            print("adding new global communities > local instance (this will take a while)...")
            for idx, actor_id in enumerate(all_actors, 1):
                if actor_id not in local_community_actor_id_list:
                    time.sleep(rl_sleep)
                    actor_resp = curSession.get(
                        "https://"
                        + local_instance
                        + "/search?q="
                        + actor_id
                        + "&type=All&listingType=All&page=1&sort=TopAll",
                        headers={"Cookie": "jwt=" + auth_token},
                    )
                    print("\r\033[K", end="")
                    print(
                        str(idx)
                        + "/"
                        + all_actor_count
                        + " "
                        + actor_id
                        + ": "
                        + str(actor_resp.status_code),
                        end="\r",
                    )
                else:
                    pass
            print("\r\033[K", end="")
            print("done.")

        def subscribe():
            print("re-fetching communities ready for subscription (this might take a while)...")
            local_community_id_list = []
            new_results = True
            page = 1
            while new_results:
                time.sleep(rl_sleep)
                actor_resp = curSession.get(
                    "https://"
                    + local_instance
                    + "/api/v3/community/list?type_=All&limit=50&page="
                    + str(page)
                    + "&auth="
                    + auth_token,
                    headers={"Content-Type": "application/json"},
                )
                if actor_resp.json()["communities"] != []:
                    for community in actor_resp.json()["communities"]:
                        if community["subscribed"] == "Subscribed":
                            continue
                        if no_pending is True and community["subscribed"] == "Pending":
                            continue
                        local_community_id_list.append(community["community"]["id"])
                        print("f:added " + community["community"]["actor_id"])
                    print(page * 50, end="\r")
                    page += 1
                else:
                    new_results = False
            print("done.")
            local_community_count = str(len(local_community_id_list))
            print("found " + local_community_count + " communities to subscribe to.")
            print("subscribing " + username + " to communities (this will take a while)...")
            for idx, community_id in enumerate(local_community_id_list, 1):
                time.sleep(rl_sleep)
                curSession.post(
                    "https://" + local_instance + "/api/v3/community/follow",
                    data='{"community_id": '
                    + str(community_id)
                    + ', "follow": true, "auth": "'
                    + auth_token
                    + '"}',
                    headers={"Cookie": "jwt=" + auth_token, "Content-Type": "application/json"},
                )
                print("\r\033[K", end="\r")
                print(str(idx) + "/" + local_community_count + " " + str(community_id), end="\r")
            print("\r\033[K", end="\r")
            print("done.")

        def unsubscribe():
            print("re-fetching communities ready for un-subscription (this might take a while)...")
            local_community_id_list = []
            new_results = True
            page = 1
            while new_results:
                time.sleep(rl_sleep)
                actor_resp = curSession.get(
                    "https://"
                    + local_instance
                    + "/api/v3/community/list?type_=All&limit=50&page="
                    + str(page)
                    + "&auth="
                    + auth_token,
                    headers={"Content-Type": "application/json"},
                )
                if actor_resp.json()["communities"] != []:
                    for community in actor_resp.json()["communities"]:
                        if community["subscribed"] == "NotSubscribed":
                            continue
                        local_community_id_list.append(community["community"]["id"])
                    print(page * 50, end="\r")
                    page += 1
                else:
                    new_results = False
            print("done.")
            local_community_count = str(len(local_community_id_list))
            print("found " + local_community_count + " communities to un-subscribe from.")
            print("subscribing " + username + " to communities (this will take a while)...")
            for idx, community_id in enumerate(local_community_id_list, 1):
                time.sleep(rl_sleep)
                curSession.post(
                    "https://" + local_instance + "/api/v3/community/follow",
                    data='{"community_id": '
                    + str(community_id)
                    + ', "follow": false, "auth": "'
                    + auth_token
                    + '"}',
                    headers={"Cookie": "jwt=" + auth_token, "Content-Type": "application/json"},
                )
                print("\r\033[K", end="\r")
                print(str(idx) + "/" + local_community_count + " " + str(community_id), end="\r")
            print("\r\033[K", end="\r")
            print("done.")

        def getlocalfederation():
            print("fetching local federation allow/block lists...")
            local_federation_list = []
            local_federation_list = curSession.get(
                "https://" + local_instance + "/api/v3/federated_instances"
            )
            included_instances = []
            excluded_instances = []
            for instance in local_federation_list.json()["federated_instances"]["linked"]:
                included_instances.append(instance["domain"])
            for instance in local_federation_list.json()["federated_instances"]["blocked"]:
                excluded_instances.append(instance["domain"])
            return (included_instances, excluded_instances)
        included_instances, excluded_instances = getlocalfederation()
        
        
        if args.include is not None:
            include_instances = args.include
            exclude_instances = []
            print("including: " + str(include_instances))
        elif args.exclude is not None:
            exclude_instances = args.exclude
            include_instances = []
            print("excluding: " + str(exclude_instances))
        else:
            include_instances = included_instances
            print("including: " + str(include_instances))
            exclude_instances = excluded_instances
            print("excluding: " + str(exclude_instances))
            
        if discover_only is True:
            discover()
        elif subscribe_only is True:
            subscribe()
        elif unsubscribe_all is True:
            unsubscribe()
        elif debug is True:
            getlocalfederation()
        else:
            discover()
            subscribe()
        print("done.")

    # login and get jwt token

    # calculate sleep from rate-limit

    # get allowed and disallowed instances from local instance and use these if -i and -e are not specified

    # main logic

    # done


if __name__ == "__main__":
    main()