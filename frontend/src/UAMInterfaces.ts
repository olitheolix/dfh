export interface UAMUser {
    uid: string;
    name: string;
}

export interface UAMGroup {
    uid: string;
    name: string;
    users: UAMUser[];
    children: UAMGroup[];
}

export interface POSTGroup {
    name: string;
    owner: string;
}

export interface POSTGroupMembers {
    groupId: string;
    userIds: string[];
}
