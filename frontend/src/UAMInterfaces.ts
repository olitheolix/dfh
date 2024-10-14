export interface UAMUser {
    uid: string;
    name: string;
    lanid: string
    slack: string
    email: string
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
