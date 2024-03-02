import { Paper, Grid } from '@mui/material';
import K8sAppList from './K8sAppList';


export default function ClusterOverview() {
    return (
        <Grid container spacing={3}>
            {/* Recent Orders */}
            <Grid item xs={12}>
                <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column' }}>
                    <K8sAppList />
                </Paper>
            </Grid>
        </Grid>
    )
}
