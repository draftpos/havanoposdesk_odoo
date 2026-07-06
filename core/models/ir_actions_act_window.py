from odoo import models, api

class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    @api.model
    def read(self, fields=None, load='_classic_read'):
        """
        Auto-format havanoposdesk actions to ensure:
        1. List view is always prioritized over Kanban view on the web interface.
        2. Mobile view mode automatically defaults to Kanban.
        This handles all modules dynamically without requiring explicit XML sequencing.
        """
        res = super().read(fields=fields, load=load)
        
        records = res if isinstance(res, list) else [res]
        
        for record in records:
            if not isinstance(record, dict):
                continue
                
            res_model = record.get('res_model')
            if res_model and res_model.startswith('havanoposdesk'):
                # 1. Enforce view_mode string order (list before kanban)
                if 'view_mode' in record and record['view_mode']:
                    modes = record['view_mode'].split(',')
                    if 'list' in modes and 'kanban' in modes:
                        list_idx = modes.index('list')
                        kanban_idx = modes.index('kanban')
                        if kanban_idx < list_idx:
                            modes.remove('kanban')
                            modes.insert(modes.index('list') + 1, 'kanban')
                            record['view_mode'] = ','.join(modes)
                            
                # 2. Enforce mobile_view_mode
                if 'mobile_view_mode' in record and not record.get('mobile_view_mode'):
                    if 'kanban' in record.get('view_mode', ''):
                        record['mobile_view_mode'] = 'kanban'
                        
                # 3. Enforce the actual 'views' tuple array order
                # The web client uses this array to determine the default view (index 0).
                # We sort it to strictly follow the view_mode priority order.
                if 'views' in record and isinstance(record['views'], list) and record.get('view_mode'):
                    modes = record['view_mode'].split(',')
                    mode_order = {mode: i for i, mode in enumerate(modes)}
                    
                    def view_sort_key(view_tuple):
                        v_id, v_type = view_tuple
                        return mode_order.get(v_type, 999)
                        
                    record['views'] = sorted(record['views'], key=view_sort_key)
                    
        return res
