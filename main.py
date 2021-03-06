#!/usr/bin/env python3

from fedora.client.fas2 import AccountSystem
from getpass import getpass
import python_freeipa
from python_freeipa import Client
import random
import progressbar

try:
    from settings import *
except:
    from settings_default import *

fas = AccountSystem(
    'https://admin.fedoraproject.org/accounts',
    username=fas_user,
    password=fas_pw,
)

instances = []
for instance in ipa_instances:
    ipa = Client(host=instance, verify_ssl=ipa_ssl)
    ipa.login(ipa_user, ipa_pw)
    instances.append(ipa)

if not skip_group_creation:
    # Start by creating groups
    fas_groups = fas.send_request(
        '/group/list',
        req_params={'search': group_search},
        auth=True,
        timeout=240
    )

    fas_groups = [g for g in fas_groups['groups'] if g['name'] not in ignore_groups]

    for group in progressbar.progressbar(fas_groups, redirect_stdout=True):
        print(group['name'], end='    ')
        try:
            ipa.group_add(group['name'], description=group['display_name'].strip())
            print('OK')
        except Exception as e:
            print('FAIL')
            print(e)

def chunks(data, n):
    return [data[x:x+n] for x in range(0, len(data), n)]

# Now move on to users
users = fas.send_request(
    '/user/list',
    req_params={'search': user_search},
    auth=True,
    timeout=240
)

def re_auth(instances):
    print('Re-authenticating')
    for ipa in instances:
        ipa.logout()
        ipa.login(ipa_user, ipa_pw)

groups_to_member_usernames = {}
groups_to_sponsor_usernames = {}

counter = 0

for person in progressbar.progressbar(users['people'], redirect_stdout=True):
    counter += 1
    if counter % reauth_every == 0:
        re_auth(instances)
    ipa = random.choice(instances)
    print(person['username'], end='    ')
    if person['human_name']:
        name = person['human_name'].strip()
        name_split = name.split(' ', 1)
        first_name = name_split[0].strip()
        last_name = name_split[1].strip() if len(name_split) > 1 and len(name_split[1].strip()) > 1 else '*'
    else:
        name = '*'
        first_name = '*'
        last_name = '*'
    try:
        if not only_map_groups:
            try:
                ipa.user_add(
                    person['username'],
                    first_name,
                    last_name,
                    name,
                    home_directory='/home/fedora/%s' % person['username'],
                    disabled=person['status'] != 'active',
                    # If they haven't synced yet, they must reset their password:
                    random_pass=True,
                    fasircnick=person['ircnick'].strip() if person['ircnick'] else None,
                    faslocale=person['locale'].strip() if person['locale'] else None,
                    fastimezone=person['timezone'].strip() if person['timezone'] else None,
                    fasgpgkeyid=[person['gpg_keyid'][:16].strip() if person['gpg_keyid'] else None],
                    fasclafpca=person['group_roles'].get('cla_fpca', {}).get('role_type') == 'user',
                )
                print('ADDED')
            except python_freeipa.exceptions.FreeIPAError as e:
                if e.message == 'user with name "%s" already exists' % person['username']:
                    # Update them instead
                    ipa.user_mod(
                        person['username'],
                        first_name=first_name,
                        last_name=last_name,
                        full_name=name,
                        home_directory='/home/fedora/%s' % person['username'],
                        disabled=person['status'] != 'active',
                        # If they haven't synced yet, they must reset their password:
                        random_pass=True,
                        fasircnick=person['ircnick'].strip() if person['ircnick'] else None,
                        faslocale=person['locale'].strip() if person['locale'] else None,
                        fastimezone=person['timezone'].strip() if person['timezone'] else None,
                        fasgpgkeyid=[person['gpg_keyid'][:16].strip() if person['gpg_keyid'] else None],
                        fasclafpca=person['group_roles'].get('cla_fpca', {}).get('role_type') == 'user',
                    )
                    print('UPDATED')
                else:
                    raise e

        for groupname, group in person['group_roles'].items():
            if groupname in groups_to_member_usernames:
                groups_to_member_usernames[groupname].append(person['username'])
            else:
                groups_to_member_usernames[groupname] = [person['username']]

            if group['role_type'] in ['administrator', 'sponsor']:
                if groupname in groups_to_sponsor_usernames:
                    groups_to_sponsor_usernames[groupname].append(person['username'])
                else:
                    groups_to_sponsor_usernames[groupname] = [person['username']]

    except python_freeipa.exceptions.Unauthorized as e:
        ipa.login(ipa_user, ipa_pw)
        continue
    except Exception as e:
        print('FAIL')
        print(e)


for group, members in groups_to_member_usernames.items():
    if group in ignore_groups:
        continue
    with progressbar.ProgressBar(max_value=len(members), redirect_stdout=True) as bar:
        bar.max_value = len(members)
        counter = 0
        for chunk in chunks(members, group_chunks):
            counter += 1
            try:
                instances[0].group_add_member(group, chunk, no_members=True)
                print('SUCCESS: Added %s as member to %s' % (chunk, group))
            except python_freeipa.exceptions.ValidationError as e:
                for msg in e.message['member']['user']:
                    print('NOTICE: Failed to add %s to %s: %s' % (msg[0], group, msg[1]))
                continue
            finally:
                bar.update(counter * len(chunk))


for group, sponsors in groups_to_sponsor_usernames.items():
    if group in ignore_groups:
        continue
    with progressbar.ProgressBar(max_value=len(sponsors), redirect_stdout=True) as bar:
        counter = 0
        for chunk in chunks(sponsors, group_chunks):
            counter += 1
            try:
                instances[0]._request(
                    'group_add_member_manager',
                    group,
                    { 'user': chunk })
                print('SUCCESS: Added %s as sponsor to %s' % (chunk, group))
            except python_freeipa.exceptions.ValidationError as e:
                for msg in e.message['member']['user']:
                    print('NOTICE: Failed to add %s to %s: %s' % (msg[0], group, msg[1]))
                continue
            finally:
                bar.update(counter * len(chunk))
